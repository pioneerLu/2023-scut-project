from django.db import models
import copy
import inspect
import warnings
from functools import partialmethod
from itertools import chain
import django
from django.apps import apps
from django.conf import settings
from django.core import checks
from django.core.exceptions import (NON_FIELD_ERRORS, FieldDoesNotExist, FieldError, MultipleObjectsReturned,ObjectDoesNotExist, ValidationError,)
from django.db import (DEFAULT_DB_ALIAS, DJANGO_VERSION_PICKLE_KEY, DatabaseError, connection,connections, router, transaction,)
from django.db.models import (NOT_PROVIDED, ExpressionWrapper, IntegerField, Max, Value,)
from django.db.models.constants import LOOKUP_SEP
from django.db.models.constraints import CheckConstraint, UniqueConstraint
from django.db.models.deletion import CASCADE, Collector
from django.db.models.fields.related import (ForeignObjectRel, OneToOneField, lazy_related_operation, resolve_relation,)
from django.db.models.functions import Coalesce
from django.db.models.manager import Manager
from django.db.models.options import Options
from django.db.models.query import F, Q
from django.db.models.signals import (class_prepared, post_init, post_save, pre_init, pre_save,)
from django.db.models.utils import make_model_tuple
from django.utils.encoding import force_str
from django.utils.hashable import make_hashable
from django.utils.text import capfirst, get_text_list
from django.utils.translation import gettext_lazy as lazy

class Deferred:
    def __repr__(self):
        return '<Deferred field>'

    def __str__(self):
        return '<Deferred field>'

# 创建一个Deferred对象，用于标记属性为延迟加载
DEFERRED = Deferred()

#动态创建一个新的异常类
def subclass_exception(name, bases, module, attached_to):

    return type(name, bases, {
        '__module__': module,
        '__qualname__': '%s.%s' % (attached_to.__qualname__, name),
    })


def _has_contribute_to_class(value):

    return not inspect.isclass(value) and hasattr(value, 'contribute_to_class')


# 定义一个用于所有模型的基类。
class ModelBase(type):
    def __new__(cls, name, bases, attrs, **kwargs):
        # 调用父类的构造方法
        super_new = super().__new__

        # 检查当前类是否有 ModelBase 作为基类，如果没有，则直接返回新类。
        parents = [b for b in bases if isinstance(b, ModelBase)]
        if not parents:
            return super_new(cls, name, bases, attrs)

        # 处理模块名称，将 '__module__' 属性从 attrs 中移除，并存储在 new_attrs 中。
        module = attrs.pop('__module__')
        new_attrs = {'__module__': module}
        classcell = attrs.pop('__classcell__', None)
        if classcell is not None:
            new_attrs['__classcell__'] = classcell

        # 处理 'Meta' 类，将其中可以贡献到类的属性放入 contributable_attrs 字典中。
        attr_meta = attrs.pop('Meta', None)
        contributable_attrs = {}
        for obj_name, obj in attrs.items():
            if _has_contribute_to_class(obj):
                contributable_attrs[obj_name] = obj
            else:
                new_attrs[obj_name] = obj

        # 使用 super_new 创建新类。
        new_class = super_new(cls, name, bases, new_attrs, **kwargs)

        # 处理模型的元数据，如是否抽象模型、模块标签等。
        # 将这些元数据存储在新类的 '_meta' 属性中。
        abstract = getattr(attr_meta, 'abstract', False)
        meta = attr_meta or getattr(new_class, 'Meta', None)
        base_meta = getattr(new_class, '_meta', None)
        app_label = None

        # 检查是否有明确的 app 标签。
        app_config = apps.get_containing_app_config(module)
        if getattr(meta, 'app_label', None) is None:
            if app_config is None:
                if not abstract:
                    raise RuntimeError(
                        "Model class %s.%s doesn't declare an explicit "
                        "app_label and isn't in an application in "
                        "INSTALLED_APPS." % (module, name)
                    )
            else:
                app_label = app_config.label
        new_class.add_to_class('_meta', Options(meta, app_label))

        # 如果模型不是抽象模型，添加 DoesNotExist 和 MultipleObjectsReturned 异常类。
        if not abstract:
            new_class.add_to_class(
                'DoesNotExist',
                subclass_exception(
                    'DoesNotExist',
                    tuple(
                        x.DoesNotExist for x in parents if hasattr(x, '_meta') and not x._meta.abstract
                    ) or (ObjectDoesNotExist,),
                    module,
                    attached_to=new_class))
            new_class.add_to_class(
                'MultipleObjectsReturned',
                subclass_exception(
                    'MultipleObjectsReturned',
                    tuple(
                        x.MultipleObjectsReturned for x in parents if hasattr(x, '_meta') and not x._meta.abstract
                    ) or (MultipleObjectsReturned,),
                    module,
                    attached_to=new_class))

        # 处理模型的继承关系，包括父类和父类的字段。
            
        # 创建一个新的字段字典 field_names 来存储字段名称。
        is_proxy = new_class._meta.proxy
        if is_proxy and base_meta and base_meta.swapped:
            raise TypeError("%s cannot proxy the swapped model '%s'." % (name, base_meta.swapped))
        for obj_name, obj in contributable_attrs.items():
            new_class.add_to_class(obj_name, obj)
        new_fields = chain(
            new_class._meta.local_fields,
            new_class._meta.local_many_to_many,
            new_class._meta.private_fields
        )
        field_names = {f.name for f in new_fields}

        # 处理代理模型。
        if is_proxy:
            base = None
            for parent in [kls for kls in parents if hasattr(kls, '_meta')]:
                if parent._meta.abstract:
                    if parent._meta.fields:
                        raise TypeError(
                            "Abstract base class containing model fields not "
                            "permitted for proxy model '%s'." % name
                        )
                    else:
                        continue
                if base is None:
                    base = parent
                elif parent._meta.concrete_model is not base._meta.concrete_model:
                    raise TypeError("Proxy model '%s' has more than one non-abstract model base class." % name)
            if base is None:
                raise TypeError("Proxy model '%s' has no non-abstract model base class." % name)
            new_class._meta.setup_proxy(base)
            new_class._meta.concrete_model = base._meta.concrete_model
        else:
            new_class._meta.concrete_model = new_class

        # 处理父类链接和继承的属性。
        parent_links = {}
        for base in reversed([new_class] + parents):
            if not hasattr(base, '_meta'):
                continue
            if base != new_class and not base._meta.abstract:
                continue
            for field in base._meta.local_fields:
                if isinstance(field, OneToOneField) and field.remote_field.parent_link:
                    related = resolve_relation(new_class, field.remote_field.model)
                    parent_links[make_model_tuple(related)] = field

        # 处理继承的属性和字段。
        inherited_attributes = set()
        for base in new_class.mro():
            if base not in parents or not hasattr(base, '_meta'):
                inherited_attributes.update(base.__dict__)
                continue
            parent_fields = base._meta.local_fields + base._meta.local_many_to_many
            if not base._meta.abstract:
                for field in parent_fields:
                    if field.name in field_names:
                        raise FieldError(
                            'Local field %r in class %r clashes with field of '
                            'the same name from base class %r.' % (
                                field.name,
                                name,
                                base.__name__,
                            )
                        )
                    else:
                        inherited_attributes.add(field.name)
                base = base._meta.concrete_model
                base_key = make_model_tuple(base)
                if base_key in parent_links:
                    field = parent_links[base_key]
                elif not is_proxy:
                    attr_name = '%s_ptr' % base._meta.model_name
                    field = OneToOneField(
                        base,
                        on_delete=CASCADE,
                        name=attr_name,
                        auto_created=True,
                        parent_link=True,
                    )
                    if attr_name in field_names:
                        raise FieldError(
                            "Auto-generated field '%s' in class %r for "
                            "parent_link to base class %r clashes with "
                            "declared field of the same name." % (
                                attr_name,
                                name,
                                base.__name__,
                            )
                        )
                    if not hasattr(new_class, attr_name):
                        new_class.add_to_class(attr_name, field)
                else:
                    field = None
                new_class._meta.parents[base] = field
            else:
                base_parents = base._meta.parents.copy()
                for field in parent_fields:
                    if (field.name not in field_names and
                            field.name not in new_class.__dict__ and
                            field.name not in inherited_attributes):
                        new_field = copy.deepcopy(field)
                        new_class.add_to_class(field.name, new_field)
                        if field.one_to_one:
                            for parent, parent_link in base_parents.items():
                                if field == parent_link:
                                    base_parents[parent] = new_field
                new_class._meta.parents.update(base_parents)
            for field in base._meta.private_fields:
                if field.name in field_names:
                    if not base._meta.abstract:
                        raise FieldError(
                            'Local field %r in class %r clashes with field of '
                            'the same name from base class %r.' % (
                                field.name,
                                name,
                                base.__name__,
                            )
                        )
                else:
                    field = copy.deepcopy(field)
                    if not base._meta.abstract:
                        field.mti_inherited = True
                    new_class.add_to_class(field.name, field)

        # 复制索引并存储在新类的 '_meta' 属性中。
        new_class._meta.indexes = [copy.deepcopy(idx) for idx in new_class._meta.indexes]

        # 如果是抽象模型，设置 'abstract' 为 False。
        if abstract:
            attr_meta.abstract = False
            new_class.Meta = attr_meta
            return new_class

        # 准备新类，并将其注册到应用程序的模型中。
        new_class._prepare()
        new_class._meta.apps.register_model(new_class._meta.app_label, new_class)
        return new_class

    def add_to_class(cls, name, value):
        if _has_contribute_to_class(value):
            value.contribute_to_class(cls, name)
        else:
            setattr(cls, name, value)

    def _prepare(cls):
        opts = cls._meta
        opts._prepare(cls)

        if opts.order_with_respect_to:
            cls.get_next_in_order = partialmethod(cls._get_next_or_previous_in_order, is_next=True)
            cls.get_previous_in_order = partialmethod(cls._get_next_or_previous_in_order, is_next=False)

            if opts.order_with_respect_to.remote_field:
                wrt = opts.order_with_respect_to
                remote = wrt.remote_field.model
                lazy_related_operation(make_foreign_order_accessors, cls, remote)


        if cls.__doc__ is None:
            cls.__doc__ = "%s(%s)" % (cls.__name__, ", ".join(f.name for f in opts.fields))

        get_absolute_url_override = settings.ABSOLUTE_URL_OVERRIDES.get(opts.label_lower)
        if get_absolute_url_override:
            setattr(cls, 'get_absolute_url', get_absolute_url_override)

        if not opts.managers:
            if any(f.name == 'objects' for f in opts.fields):
                raise ValueError(
                    "Model %s must specify a custom Manager, because it has a "
                    "field named 'objects'." % cls.__name__
                )
            manager = Manager()
            manager.auto_created = True
            cls.add_to_class('objects', manager)

        for index in cls._meta.indexes:
            if not index.name:
                index.set_name_with_model(cls)

        class_prepared.send(sender=cls)

    @property
    def _base_manager(cls):
        return cls._meta.base_manager

    @property
    def _default_manager(cls):
        return cls._meta.default_manager


class ModelStateFieldsCacheDescriptor:
    def __get__(self, instance, cls=None):
        if instance is None:
            return self
        res = instance.fields_cache = {}
        return res


class ModelState:
    db = None
    adding = True
    fields_cache = ModelStateFieldsCacheDescriptor()


class Model(metaclass=ModelBase):
    def __init__(self, *args, **kwargs):
        """
        模型类的构造方法，用于初始化模型实例。

        Args:
            *args: 位置参数
            **kwargs: 关键字参数

        Raises:
            TypeError: 如果模型是抽象模型（abstract=True），则无法实例化。

        Notes:
            - 该方法处理模型实例的初始化，包括属性的设置。
            - 它触发了模型的 `pre_init` 事件。
            - 根据传入的参数，分别处理位置参数和关键字参数，并将其映射到模型的字段。
            - 处理关联对象字段
            - 触发模型的 `post_init` 事件。
        """
        cls = self.__class__  # 获取当前实例所属的模型类
        opts = self._meta  # 获取模型的元数据
        _setattr = setattr  # 获取 setattr 函数的引用
        _DEFERRED = DEFERRED  # 获取 DEFERRED 的引用

        # 如果模型是抽象模型，抛出异常.
        if opts.abstract:
            raise TypeError('Abstract models cannot be instantiated.')

        # 触发模型的 pre_init 事件
        pre_init.send(sender=cls, args=args, kwargs=kwargs)

        # 创建用于跟踪模型实例状态的 _state 对象。
        self._state = ModelState()

        # 处理位置参数
        if len(args) > len(opts.concrete_fields):
            raise IndexError("Number of args exceeds number of fields")
        if not kwargs:
            fields_iter = iter(opts.concrete_fields)
            for val, field in zip(args, fields_iter):
                if val is _DEFERRED:
                    continue
                _setattr(self, field.attname, val)
        else:
            fields_iter = iter(opts.fields)
            for val, field in zip(args, fields_iter):
                if val is _DEFERRED:
                    continue
                _setattr(self, field.attname, val)
                kwargs.pop(field.name, None)

        # 处理关联对象字段，并设置默认值。
        for field in fields_iter:
            is_related_object = False

            if field.attname not in kwargs and field.column is None:
                continue
            if kwargs:
                if isinstance(field.remote_field, ForeignObjectRel):
                    try:
                        rel_obj = kwargs.pop(field.name)
                        is_related_object = True
                    except KeyError:
                        try:
                            val = kwargs.pop(field.attname)
                        except KeyError:
                            val = field.get_default()
                else:
                    try:
                        val = kwargs.pop(field.attname)
                    except KeyError:
                        val = field.get_default()
            else:
                val = field.get_default()

            # 处理关联对象字段
            if is_related_object:
                if rel_obj is not _DEFERRED:
                    _setattr(self, field.name, rel_obj)
            else:
                if val is not _DEFERRED:
                    _setattr(self, field.attname, val)

        # 处理剩余的关键字参数
        if kwargs:
            property_names = opts._property_names
            for prop in tuple(kwargs):
                try:
                    if prop in property_names or opts.get_field(prop):
                        if kwargs[prop] is not _DEFERRED:
                            _setattr(self, prop, kwargs[prop])
                        del kwargs[prop]
                except (AttributeError, FieldDoesNotExist):
                    pass
            for kwarg in kwargs:
                raise TypeError("%s() got an unexpected keyword argument '%s'" % (cls.__name__, kwarg))

        # 调用父类的构造方法完成初始化。
        super().__init__()
        post_init.send(sender=cls, instance=self)


    @classmethod
    def from_db(cls, db, field_names, values):
        """
    从数据库获取数据创建模型实例的类方法。

    Args:
        db: 数据库连接对象。
        field_names: 数据库字段名称。
        values: 数据库字段对应的值列表。

    Returns:
        返回一个新的模型实例，填充了数据库中的数据。

    Notes:
        - 该方法从数据库中查询数据后，将结果转换为模型实例。
        - 它会根据数据库字段名称和值列表创建模型实例。
        - 如果字段的值是 DEFERRED,则跳过该字段。
        - 创建新实例后，将其标记为不是新增数据（adding=False）并设置数据库连接。
    """
        if len(values) != len(cls._meta.concrete_fields):
            values_iter = iter(values)
            values = [
                next(values_iter) if f.attname in field_names else DEFERRED
                for f in cls._meta.concrete_fields
            ]
        new = cls(*values)
        new._state.adding = False
        new._state.db = db
        return new

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self)

    def __str__(self):
        return '%s object (%s)' % (self.__class__.__name__, self.pk)

    def __eq__(self, other):
        if not isinstance(other, Model):
            return NotImplemented
        if self._meta.concrete_model != other._meta.concrete_model:
            return False
        my_pk = self.pk
        if my_pk is None:
            return self is other
        return my_pk == other.pk

    def __hash__(self):
        if self.pk is None:
            raise TypeError("Model instances without primary key value are unhashable")
        return hash(self.pk)

    def __reduce__(self):
        data = self.__getstate__()
        data[DJANGO_VERSION_PICKLE_KEY] = django.__version__
        class_id = self._meta.app_label, self._meta.object_name
        return model_unpickle, (class_id,), data

    def __getstate__(self):
        """Hook to allow choosing the attributes to pickle."""
        state = self.__dict__.copy()
        state['_state'] = copy.copy(state['_state'])
        state['_state'].fields_cache = state['_state'].fields_cache.copy()

        _memoryview_attrs = []
        for attr, value in state.items():
            if isinstance(value, memoryview):
                _memoryview_attrs.append((attr, bytes(value)))
        if _memoryview_attrs:
            state['_memoryview_attrs'] = _memoryview_attrs
            for attr, value in _memoryview_attrs:
                state.pop(attr)
        return state

    def __setstate__(self, state):
        pickled_version = state.get(DJANGO_VERSION_PICKLE_KEY)
        if pickled_version:
            if pickled_version != django.__version__:
                warnings.warn(
                    "Pickled model instance's Django version %s does not "
                    "match the current version %s."
                    % (pickled_version, django.__version__),
                    RuntimeWarning,
                    stacklevel=2,
                )
        else:
            warnings.warn(
                "Pickled model instance's Django version is not specified.",
                RuntimeWarning,
                stacklevel=2,
            )
        if '_memoryview_attrs' in state:
            for attr, value in state.pop('_memoryview_attrs'):
                state[attr] = memoryview(value)
        self.__dict__.update(state)

    def _get_pk_val(self, meta=None):
        meta = meta or self._meta
        return getattr(self, meta.pk.attname)

    def _set_pk_val(self, value):
        for parent_link in self._meta.parents.values():
            if parent_link and parent_link != self._meta.pk:
                setattr(self, parent_link.target_field.attname, value)
        return setattr(self, self._meta.pk.attname, value)

    pk = property(_get_pk_val, _set_pk_val)

    def get_deferred_fields(self):

        return {
            f.attname for f in self._meta.concrete_fields
            if f.attname not in self.__dict__
        }

    def refresh_from_db(self, using=None, fields=None):
        """
    从数据库中重新加载模型实例的数据。

    Args:
        using (str, optional): 使用的数据库别名。
        fields (list, optional): 需要刷新的字段列表。默认为 None,表示刷新所有字段。

    Notes:
        - 该方法用于重新加载模型实例的数据，以确保它与数据库中的最新值匹配。
        - 可以指定要刷新的字段，如果未指定字段，则刷新所有字段。
        - 该方法会清除任何已预取的对象缓存.
        - 通过查询数据库获取具有相同主键的实例，并将其值复制到当前实例中，以更新数据。
        - 更新后，清除关联对象和字段的缓存值。
    """
        if fields is None:
            self._prefetched_objects_cache = {}
        else:
            prefetched_objects_cache = getattr(self, '_prefetched_objects_cache', ())
            for field in fields:
                if field in prefetched_objects_cache:
                    del prefetched_objects_cache[field]
                    fields.remove(field)
            if not fields:
                return
            if any(LOOKUP_SEP in f for f in fields):
                raise ValueError(
                    'Found "%s" in fields argument. Relations and transforms '
                    'are not allowed in fields.' % LOOKUP_SEP)

        hints = {'instance': self}
         # 使用模型的基础管理器查询数据库中具有相同主键的实例
        db_instance_qs = self.__class__._base_manager.db_manager(using, hints=hints).filter(pk=self.pk)


        deferred_fields = self.get_deferred_fields()
        if fields is not None:
            fields = list(fields)
            db_instance_qs = db_instance_qs.only(*fields)
        elif deferred_fields:
            fields = [f.attname for f in self._meta.concrete_fields
                      if f.attname not in deferred_fields]
            db_instance_qs = db_instance_qs.only(*fields)
   # 获取数据库中的实例
        db_instance = db_instance_qs.get()
        non_loaded_fields = db_instance.get_deferred_fields()
        for field in self._meta.concrete_fields:
            if field.attname in non_loaded_fields:

                continue
            setattr(self, field.attname, getattr(db_instance, field.attname))

            if field.is_relation and field.is_cached(self):
                field.delete_cached_value(self)


        for field in self._meta.related_objects:
            if field.is_cached(self):
                field.delete_cached_value(self)
# 更新实例的数据库连接信息
        self._state.db = db_instance._state.db

    def serializable_value(self, field_name):

        try:
            field = self._meta.get_field(field_name)
        except FieldDoesNotExist:
            return getattr(self, field_name)
        return getattr(self, field.attname)
    

def save(self, force_insert=False, force_update=False, using=None,
         update_fields=None):
    """
    保存模型实例到数据库中。

    Args:
        force_insert (bool, optional): 是否强制执行插入操作。默认为 False。
        force_update (bool, optional): 是否强制执行更新操作。默认为 False。
        using (str, optional): 使用的数据库别名。默认为 None。
        update_fields (list, optional): 仅更新指定字段的列表。默认为 None。

    Raises:
        ValueError: 如果同时设置了 force_insert 和 force_update。

    Notes:
        - 该方法用于将模型实例的数据保存到数据库中。
        - 可以选择性地强制执行插入或更新操作，或者指定要更新的字段。
    """
    # 准备与保存相关的字段
    self._prepare_related_fields_for_save(operation_name='save')

    # 如果未指定使用的数据库别名，则根据模型和实例选择一个
    using = using or router.db_for_write(self.__class__, instance=self)

    # 如果同时强制插入和强制更新，抛出异常
    if force_insert and (force_update or update_fields):
        raise ValueError("Cannot force both insert and updating in model saving.")

    # 获取延迟加载的字段列表
    deferred_fields = self.get_deferred_fields()

    # 处理 update_fields 参数
    if update_fields is not None:
        if not update_fields:
            return
        update_fields = frozenset(update_fields)
        field_names = set()

        # 获取模型的具体字段名称
        for field in self._meta.concrete_fields:
            if not field.primary_key:
                field_names.add(field.name)
                if field.name != field.attname:
                    field_names.add(field.attname)

        # 检查非模型字段是否存在于 update_fields 中
        non_model_fields = update_fields.difference(field_names)
        if non_model_fields:
            raise ValueError(
                'The following fields do not exist in this model, are m2m '
                'fields, or are non-concrete fields: %s'
                % ', '.join(non_model_fields)
            )

    # 处理没有指定 update_fields 的情况
    elif not force_insert and deferred_fields and using == self._state.db:
        field_names = set()
        for field in self._meta.concrete_fields:
            if not field.primary_key and not hasattr(field, 'through'):
                field_names.add(field.attname)
        loaded_fields = field_names.difference(deferred_fields)
        if loaded_fields:
            update_fields = frozenset(loaded_fields)

    # 调用底层的 save_base 方法来执行实际的保存操作
    self.save_base(using=using, force_insert=force_insert,
                   force_update=force_update, update_fields=update_fields)

    # 标记该方法会修改数据
    save.alters_data = True

    def save_base(self, raw=False, force_insert=False,
                  force_update=False, using=None, update_fields=None):

        using = using or router.db_for_write(self.__class__, instance=self)
        assert not (force_insert and (force_update or update_fields))
        assert update_fields is None or update_fields
        cls = origin = self.__class__

        if cls._meta.proxy:
            cls = cls._meta.concrete_model
        meta = cls._meta
        if not meta.auto_created:
            pre_save.send(
                sender=origin, instance=self, raw=raw, using=using,
                update_fields=update_fields,
            )

        if meta.parents:
            context_manager = transaction.atomic(using=using, savepoint=False)
        else:
            context_manager = transaction.mark_for_rollback_on_error(using=using)
        with context_manager:
            parent_inserted = False
            if not raw:
                parent_inserted = self._save_parents(cls, using, update_fields)
            updated = self._save_table(
                raw, cls, force_insert or parent_inserted,
                force_update, using, update_fields,
            )

        self._state.db = using

        self._state.adding = False

        if not meta.auto_created:
            post_save.send(
                sender=origin, instance=self, created=(not updated),
                update_fields=update_fields, raw=raw, using=using,
            )

    save_base.alters_data = True

    def _save_parents(self, cls, using, update_fields):
        """Save all the parents of cls using values from self."""
        meta = cls._meta
        inserted = False
        for parent, field in meta.parents.items():
            # Make sure the link fields are synced between parent and self.
            if (field and getattr(self, parent._meta.pk.attname) is None and
                    getattr(self, field.attname) is not None):
                setattr(self, parent._meta.pk.attname, getattr(self, field.attname))
            parent_inserted = self._save_parents(cls=parent, using=using, update_fields=update_fields)
            updated = self._save_table(
                cls=parent, using=using, update_fields=update_fields,
                force_insert=parent_inserted,
            )
            if not updated:
                inserted = True

            if field:
                setattr(self, field.attname, self._get_pk_val(parent._meta))

                if field.is_cached(self):
                    field.delete_cached_value(self)
        return inserted

    def _save_table(self, raw=False, cls=None, force_insert=False,
                    force_update=False, using=None, update_fields=None):

        meta = cls._meta
        non_pks = [f for f in meta.local_concrete_fields if not f.primary_key]

        if update_fields:
            non_pks = [f for f in non_pks
                       if f.name in update_fields or f.attname in update_fields]

        pk_val = self._get_pk_val(meta)
        if pk_val is None:
            pk_val = meta.pk.get_pk_value_on_save(self)
            setattr(self, meta.pk.attname, pk_val)
        pk_set = pk_val is not None
        if not pk_set and (force_update or update_fields):
            raise ValueError("Cannot force an update in save() with no primary key.")
        updated = False

        if (
            not raw and
            not force_insert and
            self._state.adding and
            meta.pk.default and
            meta.pk.default is not NOT_PROVIDED
        ):
            force_insert = True

        if pk_set and not force_insert:
            base_qs = cls._base_manager.using(using)
            values = [(f, None, (getattr(self, f.attname) if raw else f.pre_save(self, False)))
                      for f in non_pks]
            forced_update = update_fields or force_update
            updated = self._do_update(base_qs, using, pk_val, values, update_fields,
                                      forced_update)
            if force_update and not updated:
                raise DatabaseError("Forced update did not affect any rows.")
            if update_fields and not updated:
                raise DatabaseError("Save with update_fields did not affect any rows.")
        if not updated:
            if meta.order_with_respect_to:

                field = meta.order_with_respect_to
                filter_args = field.get_filter_kwargs_for_object(self)
                self._order = cls._base_manager.using(using).filter(**filter_args).aggregate(
                    _order__max=Coalesce(
                        ExpressionWrapper(Max('_order') + Value(1), output_field=IntegerField()),
                        Value(0),
                    ),
                )['_order__max']
            fields = meta.local_concrete_fields
            if not pk_set:
                fields = [f for f in fields if f is not meta.auto_field]

            returning_fields = meta.db_returning_fields
            results = self._do_insert(cls._base_manager, using, fields, returning_fields, raw)
            if results:
                for value, field in zip(results[0], returning_fields):
                    setattr(self, field.attname, value)
        return updated

    def _do_update(self, base_qs, using, pk_val, values, update_fields, forced_update):

        filtered = base_qs.filter(pk=pk_val)
        if not values:

            return update_fields is not None or filtered.exists()
        if self._meta.select_on_save and not forced_update:
            return (
                filtered.exists() and

                (filtered._update(values) > 0 or filtered.exists())
            )
        return filtered._update(values) > 0

    def _do_insert(self, manager, using, fields, returning_fields, raw):

        return manager._insert(
            [self], fields=fields, returning_fields=returning_fields,
            using=using, raw=raw,
        )

    def _prepare_related_fields_for_save(self, operation_name):

        for field in self._meta.concrete_fields:
            if field.is_relation and field.is_cached(self):
                obj = getattr(self, field.name, None)
                if not obj:
                    continue

                if obj.pk is None:

                    if not field.remote_field.multiple:
                        field.remote_field.delete_cached_value(obj)
                    raise ValueError(
                        "%s() prohibited to prevent data loss due to unsaved "
                        "related object '%s'." % (operation_name, field.name)
                    )
                elif getattr(self, field.attname) in field.empty_values:
                    setattr(self, field.attname, obj.pk)
                if getattr(obj, field.target_field.attname) != getattr(self, field.attname):
                    field.delete_cached_value(self)

    def delete(self, using=None, keep_parents=False):
        #从数据库中删除模型实例。
        '''
        Args:
        using (str, optional): 使用的数据库别名。默认为 None。
        keep_parents (bool, optional): 是否保留父模型的数据。默认为 False。

    Raises:
        AssertionError: 如果模型实例的主键（pk）为 None，则抛出异常。

    Returns:
        int: 返回删除的对象数量
        '''
        using = using or router.db_for_write(self.__class__, instance=self)
        assert self.pk is not None, (
            "%s object can't be deleted because its %s attribute is set to None." %
            (self._meta.object_name, self._meta.pk.attname)
        )

        collector = Collector(using=using)
        collector.collect([self], keep_parents=keep_parents)
        return collector.delete()

    delete.alters_data = True

    def _get_FIELD_display(self, field):
        value = getattr(self, field.attname)
        choices_dict = dict(make_hashable(field.flatchoices))
        # force_str() to coerce lazy strings.
        return force_str(choices_dict.get(make_hashable(value), value), strings_only=True)

    def _get_next_or_previous_by_FIELD(self, field, is_next, **kwargs):
        if not self.pk:
            raise ValueError("get_next/get_previous cannot be used on unsaved objects.")
        op = 'gt' if is_next else 'lt'
        order = '' if is_next else '-'
        param = getattr(self, field.attname)
        q = Q(**{'%s__%s' % (field.name, op): param})
        q = q | Q(**{field.name: param, 'pk__%s' % op: self.pk})
        qs = self.__class__._default_manager.using(self._state.db).filter(**kwargs).filter(q).order_by(
            '%s%s' % (order, field.name), '%spk' % order
        )
        try:
            return qs[0]
        except IndexError:
            raise self.DoesNotExist("%s matching query does not exist." % self.__class__._meta.object_name)

    def _get_next_or_previous_in_order(self, is_next):
        cachename = "__%s_order_cache" % is_next
        if not hasattr(self, cachename):
            op = 'gt' if is_next else 'lt'
            order = '_order' if is_next else '-_order'
            order_field = self._meta.order_with_respect_to
            filter_args = order_field.get_filter_kwargs_for_object(self)
            obj = self.__class__._default_manager.filter(**filter_args).filter(**{
                '_order__%s' % op: self.__class__._default_manager.values('_order').filter(**{
                    self._meta.pk.name: self.pk
                })
            }).order_by(order)[:1].get()
            setattr(self, cachename, obj)
        return getattr(self, cachename)

    def prepare_database_save(self, field):
        if self.pk is None:
            raise ValueError("Unsaved model instance %r cannot be used in an ORM query." % self)
        return getattr(self, field.remote_field.get_related_field().attname)

    def clean(self):

        pass

    def validate_unique(self, exclude=None):

        unique_checks, date_checks = self._get_unique_checks(exclude=exclude)

        errors = self._perform_unique_checks(unique_checks)
        date_errors = self._perform_date_checks(date_checks)

        for k, v in date_errors.items():
            errors.setdefault(k, []).extend(v)

        if errors:
            raise ValidationError(errors)

    def _get_unique_checks(self, exclude=None):
        if exclude is None:
            exclude = []
        unique_checks = []

        unique_togethers = [(self.__class__, self._meta.unique_together)]
        constraints = [(self.__class__, self._meta.total_unique_constraints)]
        for parent_class in self._meta.get_parent_list():
            if parent_class._meta.unique_together:
                unique_togethers.append((parent_class, parent_class._meta.unique_together))
            if parent_class._meta.total_unique_constraints:
                constraints.append(
                    (parent_class, parent_class._meta.total_unique_constraints)
                )

        for model_class, unique_together in unique_togethers:
            for check in unique_together:
                if not any(name in exclude for name in check):
                    # Add the check if the field isn't excluded.
                    unique_checks.append((model_class, tuple(check)))

        for model_class, model_constraints in constraints:
            for constraint in model_constraints:
                if not any(name in exclude for name in constraint.fields):
                    unique_checks.append((model_class, constraint.fields))

        date_checks = []


        fields_with_class = [(self.__class__, self._meta.local_fields)]
        for parent_class in self._meta.get_parent_list():
            fields_with_class.append((parent_class, parent_class._meta.local_fields))

        for model_class, fields in fields_with_class:
            for f in fields:
                name = f.name
                if name in exclude:
                    continue
                if f.unique:
                    unique_checks.append((model_class, (name,)))
                if f.unique_for_date and f.unique_for_date not in exclude:
                    date_checks.append((model_class, 'date', name, f.unique_for_date))
                if f.unique_for_year and f.unique_for_year not in exclude:
                    date_checks.append((model_class, 'year', name, f.unique_for_year))
                if f.unique_for_month and f.unique_for_month not in exclude:
                    date_checks.append((model_class, 'month', name, f.unique_for_month))
        return unique_checks, date_checks

    def _perform_unique_checks(self, unique_checks):
        """
        执行唯一性检查，检查模型实例是否满足唯一性约束。

        Args:
            unique_checks (list): 包含唯一性约束的列表。

        Returns:
            dict: 包含错误信息的字典，如果没有错误则为空字典。

        Notes:
            - 该方法用于执行唯一性检查，以确保模型实例满足唯一性约束。
            - 唯一性约束是通过 unique_checks 参数传递的，每个约束是一个元组，
            元组的第一个元素是相关的模型类，第二个元素是字段名称列表。
            - 对于每个唯一性约束，方法会创建一个查询，检查数据库中是否存在与当前模型实例匹配的记录。
            - 如果存在重复记录，则将错误信息添加到返回的字典中。
        """
        errors = {}

        for model_class, unique_check in unique_checks:

            lookup_kwargs = {}
            for field_name in unique_check:
                f = self._meta.get_field(field_name)
                lookup_value = getattr(self, f.attname)

                # 处理空值和空字符串是否视为空值的情况
                if (lookup_value is None or
                        (lookup_value == '' and connection.features.interprets_empty_strings_as_nulls)):

                    continue

                # 处理主键字段的情况，如果不是新增记录，则跳过
                if f.primary_key and not self._state.adding:
                    continue

                lookup_kwargs[str(field_name)] = lookup_value

            # 如果字段数量不匹配，跳过当前约束
            if len(unique_check) != len(lookup_kwargs):
                continue

            # 创建查询，检查是否存在与当前模型实例匹配的记录
            qs = model_class._default_manager.filter(**lookup_kwargs)

            # 排除当前模型实例本身（如果不是新增记录）
            model_class_pk = self._get_pk_val(model_class._meta)
            if not self._state.adding and model_class_pk is not None:
                qs = qs.exclude(pk=model_class_pk)

            # 如果查询结果存在记录，则添加错误信息到字典中
            if qs.exists():
                if len(unique_check) == 1:
                    key = unique_check[0]
                else:
                    key = NON_FIELD_ERRORS
                errors.setdefault(key, []).append(self.unique_error_message(model_class, unique_check))

            return errors

    def _perform_unique_checks(self, unique_checks):
        """
        执行唯一性检查，检查模型实例是否满足唯一性约束。

        Args:
            unique_checks (list): 包含唯一性约束的列表。

        Returns:
            dict: 包含错误信息的字典，如果没有错误则为空字典。

        Notes:
            - 该方法用于执行唯一性检查，以确保模型实例满足唯一性约束。
            - 唯一性约束通过 unique_checks 参数传递，每个约束是一个元组，
        """
        errors = {}

        for model_class, unique_check in unique_checks:

            lookup_kwargs = {}
            for field_name in unique_check:
                f = self._meta.get_field(field_name)
                lookup_value = getattr(self, f.attname)

                # 处理空值和空字符串是否视为空值的情况
                if (lookup_value is None or
                        (lookup_value == '' and connection.features.interprets_empty_strings_as_nulls)):

                    continue

                # 处理主键字段的情况，如果不是新增记录，则跳过
                if f.primary_key and not self._state.adding:
                    continue

                lookup_kwargs[str(field_name)] = lookup_value

            # 如果字段数量不匹配，跳过当前约束
            if len(unique_check) != len(lookup_kwargs):
                continue

            # 创建查询，检查是否存在与当前模型实例匹配的记录
            qs = model_class._default_manager.filter(**lookup_kwargs)

            # 排除当前模型实例本身（如果不是新增记录）
            model_class_pk = self._get_pk_val(model_class._meta)
            if not self._state.adding and model_class_pk is not None:
                qs = qs.exclude(pk=model_class_pk)

            # 如果查询结果存在记录，则添加错误信息到字典中
            if qs.exists():
                if len(unique_check) == 1:
                    key = unique_check[0]
                else:
                    key = NON_FIELD_ERRORS
                errors.setdefault(key, []).append(self.unique_error_message(model_class, unique_check))

            return errors


    def date_error_message(self, lookup_type, field_name, unique_for):
        opts = self._meta
        field = opts.get_field(field_name)
        return ValidationError(
            message=field.error_messages['unique_for_date'],
            code='unique_for_date',
            params={
                'model': self,
                'model_name': capfirst(opts.verbose_name),
                'lookup_type': lookup_type,
                'field': field_name,
                'field_label': capfirst(field.verbose_name),
                'date_field': unique_for,
                'date_field_label': capfirst(opts.get_field(unique_for).verbose_name),
            }
        )

    def unique_error_message(self, model_class, unique_check):
        opts = model_class._meta

        params = {
            'model': self,
            'model_class': model_class,
            'model_name': capfirst(opts.verbose_name),
            'unique_check': unique_check,
        }


        if len(unique_check) == 1:
            field = opts.get_field(unique_check[0])
            params['field_label'] = capfirst(field.verbose_name)
            return ValidationError(
                message=field.error_messages['unique'],
                code='unique',
                params=params,
            )


        else:
            field_labels = [capfirst(opts.get_field(f).verbose_name) for f in unique_check]
            params['field_labels'] = get_text_list(field_labels, lazy('and'))
            return ValidationError(
                message=lazy("%(model_name)s with this %(field_labels)s already exists."),
                code='unique_together',
                params=params,
            )

    def full_clean(self, exclude=None, validate_unique=True):
        errors = {}
        if exclude is None:
            exclude = []
        else:
            exclude = list(exclude)

        try:
            self.clean_fields(exclude=exclude)
        except ValidationError as e:
            errors = e.update_error_dict(errors)


        try:
            self.clean()
        except ValidationError as e:
            errors = e.update_error_dict(errors)

        if validate_unique:
            for name in errors:
                if name != NON_FIELD_ERRORS and name not in exclude:
                    exclude.append(name)
            try:
                self.validate_unique(exclude=exclude)
            except ValidationError as e:
                errors = e.update_error_dict(errors)

        if errors:
            raise ValidationError(errors)

    def clean_fields(self, exclude=None):

        if exclude is None:
            exclude = []

        errors = {}
        for f in self._meta.fields:
            if f.name in exclude:
                continue
            raw_value = getattr(self, f.attname)
            if f.blank and raw_value in f.empty_values:
                continue
            try:
                setattr(self, f.attname, f.clean(raw_value, self))
            except ValidationError as e:
                errors[f.name] = e.error_list

        if errors:
            raise ValidationError(errors)

    @classmethod
    def check(cls, **kwargs):
        errors = [*cls._check_swappable(), *cls._check_model(), *cls._check_managers(**kwargs)]
        if not cls._meta.swapped:
            databases = kwargs.get('databases') or []
            errors += [
                *cls._check_fields(**kwargs),
                *cls._check_m2m_through_same_relationship(),
                *cls._check_long_column_names(databases),
            ]
            clash_errors = (
                *cls._check_id_field(),
                *cls._check_field_name_clashes(),
                *cls._check_model_name_db_lookup_clashes(),
                *cls._check_property_name_related_field_accessor_clashes(),
                *cls._check_single_primary_key(),
            )
            errors.extend(clash_errors)

            if not clash_errors:
                errors.extend(cls._check_column_name_clashes())
            errors += [
                *cls._check_index_together(),
                *cls._check_unique_together(),
                *cls._check_indexes(databases),
                *cls._check_ordering(),
                *cls._check_constraints(databases),
                *cls._check_default_pk(),
            ]

        return errors

    @classmethod
    def _check_default_pk(cls):
        if (
            not cls._meta.abstract and
            cls._meta.pk.auto_created and

            not (
                isinstance(cls._meta.pk, OneToOneField) and
                cls._meta.pk.remote_field.parent_link
            ) and
            not settings.is_overridden('DEFAULT_AUTO_FIELD') and
            cls._meta.app_config and
            not cls._meta.app_config._is_default_auto_field_overridden
        ):
            return [
                checks.Warning(
                    f"Auto-created primary key used when not defining a "
                    f"primary key type, by default "
                    f"'{settings.DEFAULT_AUTO_FIELD}'.",
                    hint=(
                        f"Configure the DEFAULT_AUTO_FIELD setting or the "
                        f"{cls._meta.app_config.__class__.__qualname__}."
                        f"default_auto_field attribute to point to a subclass "
                        f"of AutoField, e.g. 'django.db.models.BigAutoField'."
                    ),
                    obj=cls,
                    id='models.W042',
                ),
            ]
        return []

    @classmethod
    def _check_swappable(cls):
        errors = []
        if cls._meta.swapped:
            try:
                apps.get_model(cls._meta.swapped)
            except ValueError:
                errors.append(
                    checks.Error(
                        "'%s' is not of the form 'app_label.app_name'." % cls._meta.swappable,
                        id='models.E001',
                    )
                )
            except LookupError:
                app_label, model_name = cls._meta.swapped.split('.')
                errors.append(
                    checks.Error(
                        "'%s' references '%s.%s', which has not been "
                        "installed, or is abstract." % (
                            cls._meta.swappable, app_label, model_name
                        ),
                        id='models.E002',
                    )
                )
        return errors

    @classmethod
    def _check_model(cls):
        errors = []
        if cls._meta.proxy:
            if cls._meta.local_fields or cls._meta.local_many_to_many:
                errors.append(
                    checks.Error(
                        "Proxy model '%s' contains model fields." % cls.__name__,
                        id='models.E017',
                    )
                )
        return errors

    @classmethod
    def _check_managers(cls, **kwargs):
        """Perform all manager checks."""
        errors = []
        for manager in cls._meta.managers:
            errors.extend(manager.check(**kwargs))
        return errors

    @classmethod
    def _check_fields(cls, **kwargs):

        errors = []
        for field in cls._meta.local_fields:
            errors.extend(field.check(**kwargs))
        for field in cls._meta.local_many_to_many:
            errors.extend(field.check(from_model=cls, **kwargs))
        return errors

    @classmethod
    def _check_m2m_through_same_relationship(cls):

        errors = []
        seen_intermediary_signatures = []

        fields = cls._meta.local_many_to_many


        fields = (f for f in fields if isinstance(f.remote_field.model, ModelBase))


        fields = (f for f in fields if isinstance(f.remote_field.through, ModelBase))

        for f in fields:
            signature = (f.remote_field.model, cls, f.remote_field.through, f.remote_field.through_fields)
            if signature in seen_intermediary_signatures:
                errors.append(
                    checks.Error(
                        "The model has two identical many-to-many relations "
                        "through the intermediate model '%s'." %
                        f.remote_field.through._meta.label,
                        obj=cls,
                        id='models.E003',
                    )
                )
            else:
                seen_intermediary_signatures.append(signature)
        return errors

    @classmethod
    def _check_id_field(cls):
        """Check if `id` field is a primary key."""
        fields = [f for f in cls._meta.local_fields if f.name == 'id' and f != cls._meta.pk]
        # fields is empty or consists of the invalid "id" field
        if fields and not fields[0].primary_key and cls._meta.pk.name == 'id':
            return [
                checks.Error(
                    "'id' can only be used as a field name if the field also "
                    "sets 'primary_key=True'.",
                    obj=cls,
                    id='models.E004',
                )
            ]
        else:
            return []

    @classmethod
    def _check_field_name_clashes(cls):
        errors = []
        used_fields = {}

        for parent in cls._meta.get_parent_list():
            for f in parent._meta.local_fields:
                clash = used_fields.get(f.name) or used_fields.get(f.attname) or None
                if clash:
                    errors.append(
                        checks.Error(
                            "The field '%s' from parent model "
                            "'%s' clashes with the field '%s' "
                            "from parent model '%s'." % (
                                clash.name, clash.model._meta,
                                f.name, f.model._meta
                            ),
                            obj=cls,
                            id='models.E005',
                        )
                    )
                used_fields[f.name] = f
                used_fields[f.attname] = f


        for parent in cls._meta.get_parent_list():
            for f in parent._meta.get_fields():
                if f not in used_fields:
                    used_fields[f.name] = f

        for f in cls._meta.local_fields:
            clash = used_fields.get(f.name) or used_fields.get(f.attname) or None
            id_conflict = f.name == "id" and clash and clash.name == "id" and clash.model == cls
            if clash and not id_conflict:
                errors.append(
                    checks.Error(
                        "The field '%s' clashes with the field '%s' "
                        "from model '%s'." % (
                            f.name, clash.name, clash.model._meta
                        ),
                        obj=f,
                        id='models.E006',
                    )
                )
            used_fields[f.name] = f
            used_fields[f.attname] = f

        return errors

    @classmethod
    def _check_column_name_clashes(cls):

        used_column_names = []
        errors = []

        for f in cls._meta.local_fields:
            _, column_name = f.get_attname_column()


            if column_name and column_name in used_column_names:
                errors.append(
                    checks.Error(
                        "Field '%s' has column name '%s' that is used by "
                        "another field." % (f.name, column_name),
                        hint="Specify a 'db_column' for the field.",
                        obj=cls,
                        id='models.E007'
                    )
                )
            else:
                used_column_names.append(column_name)

        return errors

    @classmethod
    def _check_model_name_db_lookup_clashes(cls):
        errors = []
        model_name = cls.__name__
        if model_name.startswith('_') or model_name.endswith('_'):
            errors.append(
                checks.Error(
                    "The model name '%s' cannot start or end with an underscore "
                    "as it collides with the query lookup syntax." % model_name,
                    obj=cls,
                    id='models.E023'
                )
            )
        elif LOOKUP_SEP in model_name:
            errors.append(
                checks.Error(
                    "The model name '%s' cannot contain double underscores as "
                    "it collides with the query lookup syntax." % model_name,
                    obj=cls,
                    id='models.E024'
                )
            )
        return errors

    @classmethod
    def _check_property_name_related_field_accessor_clashes(cls):
        errors = []
        property_names = cls._meta._property_names
        related_field_accessors = (
            f.get_attname() for f in cls._meta._get_fields(reverse=False)
            if f.is_relation and f.related_model is not None
        )
        for accessor in related_field_accessors:
            if accessor in property_names:
                errors.append(
                    checks.Error(
                        "The property '%s' clashes with a related field "
                        "accessor." % accessor,
                        obj=cls,
                        id='models.E025',
                    )
                )
        return errors

    @classmethod
    def _check_single_primary_key(cls):
        errors = []
        if sum(1 for f in cls._meta.local_fields if f.primary_key) > 1:
            errors.append(
                checks.Error(
                    "The model cannot have more than one field with "
                    "'primary_key=True'.",
                    obj=cls,
                    id='models.E026',
                )
            )
        return errors

    @classmethod
    def _check_index_together(cls):
        """Check the value of "index_together" option."""
        if not isinstance(cls._meta.index_together, (tuple, list)):
            return [
                checks.Error(
                    "'index_together' must be a list or tuple.",
                    obj=cls,
                    id='models.E008',
                )
            ]

        elif any(not isinstance(fields, (tuple, list)) for fields in cls._meta.index_together):
            return [
                checks.Error(
                    "All 'index_together' elements must be lists or tuples.",
                    obj=cls,
                    id='models.E009',
                )
            ]

        else:
            errors = []
            for fields in cls._meta.index_together:
                errors.extend(cls._check_local_fields(fields, "index_together"))
            return errors

    @classmethod
    def _check_unique_together(cls):

        if not isinstance(cls._meta.unique_together, (tuple, list)):
            return [
                checks.Error(
                    "'unique_together' must be a list or tuple.",
                    obj=cls,
                    id='models.E010',
                )
            ]

        elif any(not isinstance(fields, (tuple, list)) for fields in cls._meta.unique_together):
            return [
                checks.Error(
                    "All 'unique_together' elements must be lists or tuples.",
                    obj=cls,
                    id='models.E011',
                )
            ]

        else:
            errors = []
            for fields in cls._meta.unique_together:
                errors.extend(cls._check_local_fields(fields, "unique_together"))
            return errors

    @classmethod
    def _check_indexes(cls, databases):

        errors = []
        references = set()
        for index in cls._meta.indexes:
            if index.name[0] == '_' or index.name[0].isdigit():
                errors.append(
                    checks.Error(
                        "The index name '%s' cannot start with an underscore "
                        "or a number." % index.name,
                        obj=cls,
                        id='models.E033',
                    ),
                )
            if len(index.name) > index.max_name_length:
                errors.append(
                    checks.Error(
                        "The index name '%s' cannot be longer than %d "
                        "characters." % (index.name, index.max_name_length),
                        obj=cls,
                        id='models.E034',
                    ),
                )
            if index.contains_expressions:
                for expression in index.expressions:
                    references.update(
                        ref[0] for ref in cls._get_expr_references(expression)
                    )
        for db in databases:
            if not router.allow_migrate_model(db, cls):
                continue
            connection = connections[db]
            if not (
                connection.features.supports_partial_indexes or
                'supports_partial_indexes' in cls._meta.required_db_features
            ) and any(index.condition is not None for index in cls._meta.indexes):
                errors.append(
                    checks.Warning(
                        '%s does not support indexes with conditions.'
                        % connection.display_name,
                        hint=(
                            "Conditions will be ignored. Silence this warning "
                            "if you don't care about it."
                        ),
                        obj=cls,
                        id='models.W037',
                    )
                )
            if not (
                connection.features.supports_covering_indexes or
                'supports_covering_indexes' in cls._meta.required_db_features
            ) and any(index.include for index in cls._meta.indexes):
                errors.append(
                    checks.Warning(
                        '%s does not support indexes with non-key columns.'
                        % connection.display_name,
                        hint=(
                            "Non-key columns will be ignored. Silence this "
                            "warning if you don't care about it."
                        ),
                        obj=cls,
                        id='models.W040',
                    )
                )
            if not (
                connection.features.supports_expression_indexes or
                'supports_expression_indexes' in cls._meta.required_db_features
            ) and any(index.contains_expressions for index in cls._meta.indexes):
                errors.append(
                    checks.Warning(
                        '%s does not support indexes on expressions.'
                        % connection.display_name,
                        hint=(
                            "An index won't be created. Silence this warning "
                            "if you don't care about it."
                        ),
                        obj=cls,
                        id='models.W043',
                    )
                )
        fields = [field for index in cls._meta.indexes for field, _ in index.fields_orders]
        fields += [include for index in cls._meta.indexes for include in index.include]
        fields += references
        errors.extend(cls._check_local_fields(fields, 'indexes'))
        return errors

    @classmethod
    def _check_local_fields(cls, fields, option):
        from django.db import models

        forward_fields_map = {}
        for field in cls._meta._get_fields(reverse=False):
            forward_fields_map[field.name] = field
            if hasattr(field, 'attname'):
                forward_fields_map[field.attname] = field

        errors = []
        for field_name in fields:
            try:
                field = forward_fields_map[field_name]
            except KeyError:
                errors.append(
                    checks.Error(
                        "'%s' refers to the nonexistent field '%s'." % (
                            option, field_name,
                        ),
                        obj=cls,
                        id='models.E012',
                    )
                )
            else:
                if isinstance(field.remote_field, models.ManyToManyRel):
                    errors.append(
                        checks.Error(
                            "'%s' refers to a ManyToManyField '%s', but "
                            "ManyToManyFields are not permitted in '%s'." % (
                                option, field_name, option,
                            ),
                            obj=cls,
                            id='models.E013',
                        )
                    )
                elif field not in cls._meta.local_fields:
                    errors.append(
                        checks.Error(
                            "'%s' refers to field '%s' which is not local to model '%s'."
                            % (option, field_name, cls._meta.object_name),
                            hint="This issue may be caused by multi-table inheritance.",
                            obj=cls,
                            id='models.E016',
                        )
                    )
        return errors

    @classmethod
    def _check_ordering(cls):
        if cls._meta._ordering_clash:
            return [
                checks.Error(
                    "'ordering' and 'order_with_respect_to' cannot be used together.",
                    obj=cls,
                    id='models.E021',
                ),
            ]

        if cls._meta.order_with_respect_to or not cls._meta.ordering:
            return []

        if not isinstance(cls._meta.ordering, (list, tuple)):
            return [
                checks.Error(
                    "'ordering' must be a tuple or list (even if you want to order by only one field).",
                    obj=cls,
                    id='models.E014',
                )
            ]

        errors = []
        fields = cls._meta.ordering

        fields = (f for f in fields if isinstance(f, str) and f != '?')

        fields = ((f[1:] if f.startswith('-') else f) for f in fields)

        _fields = []
        related_fields = []
        for f in fields:
            if LOOKUP_SEP in f:
                related_fields.append(f)
            else:
                _fields.append(f)
        fields = _fields

        for field in related_fields:
            _cls = cls
            fld = None
            for part in field.split(LOOKUP_SEP):
                try:
                    if part == 'pk':
                        fld = _cls._meta.pk
                    else:
                        fld = _cls._meta.get_field(part)
                    if fld.is_relation:
                        _cls = fld.get_path_info()[-1].to_opts.model
                    else:
                        _cls = None
                except (FieldDoesNotExist, AttributeError):
                    if fld is None or (
                        fld.get_transform(part) is None and fld.get_lookup(part) is None
                    ):
                        errors.append(
                            checks.Error(
                                "'ordering' refers to the nonexistent field, "
                                "related field, or lookup '%s'." % field,
                                obj=cls,
                                id='models.E015',
                            )
                        )

        fields = {f for f in fields if f != 'pk'}


        invalid_fields = []


        opts = cls._meta
        valid_fields = set(chain.from_iterable(
            (f.name, f.attname) if not (f.auto_created and not f.concrete) else (f.field.related_query_name(),)
            for f in chain(opts.fields, opts.related_objects)
        ))

        invalid_fields.extend(fields - valid_fields)

        for invalid_field in invalid_fields:
            errors.append(
                checks.Error(
                    "'ordering' refers to the nonexistent field, related "
                    "field, or lookup '%s'." % invalid_field,
                    obj=cls,
                    id='models.E015',
                )
            )
        return errors

    @classmethod
    def _check_long_column_names(cls, databases):

        if not databases:
            return []
        errors = []
        allowed_len = None
        db_alias = None

        for db in databases:
            if not router.allow_migrate_model(db, cls):
                continue
            connection = connections[db]
            max_name_length = connection.ops.max_name_length()
            if max_name_length is None or connection.features.truncates_names:
                continue
            else:
                if allowed_len is None:
                    allowed_len = max_name_length
                    db_alias = db
                elif max_name_length < allowed_len:
                    allowed_len = max_name_length
                    db_alias = db

        if allowed_len is None:
            return errors

        for f in cls._meta.local_fields:
            _, column_name = f.get_attname_column()


            if f.db_column is None and column_name is not None and len(column_name) > allowed_len:
                errors.append(
                    checks.Error(
                        'Autogenerated column name too long for field "%s". '
                        'Maximum length is "%s" for database "%s".'
                        % (column_name, allowed_len, db_alias),
                        hint="Set the column name manually using 'db_column'.",
                        obj=cls,
                        id='models.E018',
                    )
                )

        for f in cls._meta.local_many_to_many:
            if isinstance(f.remote_field.through, str):
                continue

            for m2m in f.remote_field.through._meta.local_fields:
                _, rel_name = m2m.get_attname_column()
                if m2m.db_column is None and rel_name is not None and len(rel_name) > allowed_len:
                    errors.append(
                        checks.Error(
                            'Autogenerated column name too long for M2M field '
                            '"%s". Maximum length is "%s" for database "%s".'
                            % (rel_name, allowed_len, db_alias),
                            hint=(
                                "Use 'through' to create a separate model for "
                                "M2M and then set column_name using 'db_column'."
                            ),
                            obj=cls,
                            id='models.E019',
                        )
                    )

        return errors

    @classmethod
    def _get_expr_references(cls, expr):
        if isinstance(expr, Q):
            for child in expr.children:
                if isinstance(child, tuple):
                    lookup, value = child
                    yield tuple(lookup.split(LOOKUP_SEP))
                    yield from cls._get_expr_references(value)
                else:
                    yield from cls._get_expr_references(child)
        elif isinstance(expr, F):
            yield tuple(expr.name.split(LOOKUP_SEP))
        elif hasattr(expr, 'get_source_expressions'):
            for src_expr in expr.get_source_expressions():
                yield from cls._get_expr_references(src_expr)

    @classmethod
    def _check_constraints(cls, databases):
        errors = []
        for db in databases:
            if not router.allow_migrate_model(db, cls):
                continue
            connection = connections[db]
            if not (
                connection.features.supports_table_check_constraints or
                'supports_table_check_constraints' in cls._meta.required_db_features
            ) and any(
                isinstance(constraint, CheckConstraint)
                for constraint in cls._meta.constraints
            ):
                errors.append(
                    checks.Warning(
                        '%s does not support check constraints.' % connection.display_name,
                        hint=(
                            "A constraint won't be created. Silence this "
                            "warning if you don't care about it."
                        ),
                        obj=cls,
                        id='models.W027',
                    )
                )
            if not (
                connection.features.supports_partial_indexes or
                'supports_partial_indexes' in cls._meta.required_db_features
            ) and any(
                isinstance(constraint, UniqueConstraint) and constraint.condition is not None
                for constraint in cls._meta.constraints
            ):
                errors.append(
                    checks.Warning(
                        '%s does not support unique constraints with '
                        'conditions.' % connection.display_name,
                        hint=(
                            "A constraint won't be created. Silence this "
                            "warning if you don't care about it."
                        ),
                        obj=cls,
                        id='models.W036',
                    )
                )
            if not (
                connection.features.supports_deferrable_unique_constraints or
                'supports_deferrable_unique_constraints' in cls._meta.required_db_features
            ) and any(
                isinstance(constraint, UniqueConstraint) and constraint.deferrable is not None
                for constraint in cls._meta.constraints
            ):
                errors.append(
                    checks.Warning(
                        '%s does not support deferrable unique constraints.'
                        % connection.display_name,
                        hint=(
                            "A constraint won't be created. Silence this "
                            "warning if you don't care about it."
                        ),
                        obj=cls,
                        id='models.W038',
                    )
                )
            if not (
                connection.features.supports_covering_indexes or
                'supports_covering_indexes' in cls._meta.required_db_features
            ) and any(
                isinstance(constraint, UniqueConstraint) and constraint.include
                for constraint in cls._meta.constraints
            ):
                errors.append(
                    checks.Warning(
                        '%s does not support unique constraints with non-key '
                        'columns.' % connection.display_name,
                        hint=(
                            "A constraint won't be created. Silence this "
                            "warning if you don't care about it."
                        ),
                        obj=cls,
                        id='models.W039',
                    )
                )
            fields = set(chain.from_iterable(
                (*constraint.fields, *constraint.include)
                for constraint in cls._meta.constraints if isinstance(constraint, UniqueConstraint)
            ))
            references = set()
            for constraint in cls._meta.constraints:
                if isinstance(constraint, UniqueConstraint):
                    if (
                        connection.features.supports_partial_indexes or
                        'supports_partial_indexes' not in cls._meta.required_db_features
                    ) and isinstance(constraint.condition, Q):
                        references.update(cls._get_expr_references(constraint.condition))
                elif isinstance(constraint, CheckConstraint):
                    if (
                        connection.features.supports_table_check_constraints or
                        'supports_table_check_constraints' not in cls._meta.required_db_features
                    ) and isinstance(constraint.check, Q):
                        references.update(cls._get_expr_references(constraint.check))
            for field_name, *lookups in references:
                if field_name != 'pk':
                    fields.add(field_name)
                if not lookups:
                    continue
                try:
                    if field_name == 'pk':
                        field = cls._meta.pk
                    else:
                        field = cls._meta.get_field(field_name)
                    if not field.is_relation or field.many_to_many or field.one_to_many:
                        continue
                except FieldDoesNotExist:
                    continue
                first_lookup = lookups[0]
                if (
                    hasattr(field, 'get_transform') and
                    hasattr(field, 'get_lookup') and
                    field.get_transform(first_lookup) is None and
                    field.get_lookup(first_lookup) is None
                ):
                    errors.append(
                        checks.Error(
                            "'constraints' refers to the joined field '%s'."
                            % LOOKUP_SEP.join([field_name] + lookups),
                            obj=cls,
                            id='models.E041',
                        )
                    )
            errors.extend(cls._check_local_fields(fields, 'constraints'))
        return errors


#一些排序方法

def method_set_order(self, ordered_obj, id_list, using=None):
    if using is None:
        using = DEFAULT_DB_ALIAS
    order_wrt = ordered_obj._meta.order_with_respect_to
    filter_args = order_wrt.get_forward_related_filter(self)
    ordered_obj.objects.db_manager(using).filter(**filter_args).bulk_update([
        ordered_obj(pk=pk, _order=order) for order, pk in enumerate(id_list)
    ], ['_order'])


def method_get_order(self, ordered_obj):
    order_wrt = ordered_obj._meta.order_with_respect_to
    filter_args = order_wrt.get_forward_related_filter(self)
    pk_name = ordered_obj._meta.pk.name
    return ordered_obj.objects.filter(**filter_args).values_list(pk_name, flat=True)


def make_foreign_order_accessors(model, related_model):
    setattr(
        related_model,
        'get_%s_order' % model.__name__.lower(),
        partialmethod(method_get_order, model)
    )
    setattr(
        related_model,
        'set_%s_order' % model.__name__.lower(),
        partialmethod(method_set_order, model)
    )



def model_unpickle(model_id):
    """Used to unpickle Model subclasses with deferred fields."""
    if isinstance(model_id, tuple):
        model = apps.get_model(*model_id)
    else:

        model = model_id
    return model.__new__(model)


model_unpickle.__safe_for_unpickle__ = True

###########具象类

# 管理员
class admin(models.Model):
    id = models.AutoField(primary_key=True) # id 会自动创建,可以手动写入
    name = models.CharField(max_length=45) # 姓名
    password = models.CharField(max_length=45) # 密码

    class Meta:
        managed = False
        db_table = 'admin'

# 患者
class user_patient(models.Model):
    sex_choices = (
        (0, "女"),
        (1, "男")
    )
    id = models.AutoField(primary_key=True) # id 会自动创建,可以手动写入
    name = models.CharField(max_length=45) # 姓名
    id_card = models.CharField(max_length=45) # 身份证
    phone = models.CharField(max_length=45) # 电话
    password = models.CharField(max_length=45) # 密码
    sex = models.SmallIntegerField(choices=sex_choices) # 性别
    age = models.SmallIntegerField() # 年龄

    class Meta:
        managed = False
        db_table = 'user_patient'

#特殊病人
class SpecialPatient(user_patient):
    special_condition = models.CharField(max_length=100, blank=True, null=True)#病史情况
    emergency_contact_name = models.CharField(max_length=45, blank=True, null=True)#紧急联系人
    emergency_contact_phone = models.CharField(max_length=45, blank=True, null=True)#紧急联系人电话
    medical_history = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'special_patient'

# 医生
class user_doctor(models.Model):
    id = models.AutoField(primary_key=True) # id 会自动创建,可以手动写入
    name = models.CharField(max_length=45) # 姓名
    id_card = models.CharField(max_length=45) # 身份证
    department_id = models.SmallIntegerField() # 科室
    password = models.CharField(max_length=45) # 密码
    status = models.SmallIntegerField(default=1) # 状态

    class Meta:
        managed = False
        db_table = 'user_doctor'
#主治医师
class SuperDoctor(user_doctor):
    
    speciality = models.CharField(max_length=100, blank=True, null=True)#特级医师的专长
    experience_years = models.IntegerField(default=0)#工作年限
    research_interests = models.TextField(blank=True, null=True)#专业研究方向
    

    class Meta:
        managed = False
        db_table = 'super_doctor'


# 科室
class department(models.Model):
    id = models.AutoField(primary_key=True) # id 会自动创建,也可以手动写入
    name = models.CharField(max_length=45) # 名称
    registration_fee = models.DecimalField(max_digits=10, decimal_places=2) # 挂号费
    doctor_num = models.SmallIntegerField(default=0) # 医生数

    class Meta:
        managed = False
        db_table = 'department'

# 药品
class medicine(models.Model):
    id = models.AutoField(primary_key=True) # id 会自动创建,可以手动写入
    name = models.CharField(max_length=45) # 名称
    price = models.DecimalField(max_digits=10, decimal_places=2) # 单价
    unit = models.CharField(max_length=45) # 单位

    class Meta:
        managed = False
        db_table = 'medicine'

# 就诊、挂号
class order(models.Model):
    id = models.AutoField(primary_key=True) # id 会自动创建,可以手动写入
    patient_id = models.SmallIntegerField() # 患者id
    department_id = models.SmallIntegerField() # 科室
    readme = models.CharField(max_length=200) # 自述
    registration_fee = models.DecimalField(max_digits=10, decimal_places=2) # 挂号费
    doctor_id = models.SmallIntegerField() # 医生id
    order_advice = models.CharField(max_length=400) # 医嘱
    medicine_list = models.CharField(max_length=400) # 药列表
    total_cost = models.DecimalField(max_digits=10, decimal_places=2,default=0) # 总费用
    status = models.SmallIntegerField(default=1) # 状态
    time = models.DateTimeField(auto_now_add=True) # 创建时间

    class Meta:
        managed = False
        db_table = 'order'