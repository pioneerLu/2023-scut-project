# 基于Django框架的医院管理系统

# 开发环境
    python3.9
    PyCharm Community Edition 2022/ VScode 2022
    mysql8.0
    Navicat Premium 15

   
  ## Dependencies(开发时使用的版本，其他版本可能也能运行)
  - Django==3.2.13
  - djangorestframework==3.13.1
  - PyMySQL==1.0.2
  
  可在python Django路径下使用命令 pip install -r requirements 来完成依赖配置

# 项目结构
  -SQL：数据库
  -源码
    -hospital
      -hospital：后端python代码存放位置
      -model：Django自带框架
      -static：js及css文件存放位置
      -template：前端html代码存放位置
      -manage.py：项目启动位置
      


# 功能说明

登陆页面：
	多角色登陆（除管理员外，医生和患者登陆账户均为身份证号）
	患者注册

管理员系统
科室管理页面：
	查看科室列表
医生管理页面：
	查看已有医生列表
	添加新医生（科室填入科室编号即可）
  标记主治医师，并添加新信息
药品管理页面：
	查看已有药品列表
	添加新药品
患者管理页面：
	查看已有患者列表
	添加新患者
  标记特殊患者

患者系统（医院电子平台）
就诊大厅页面：
	挂号（选择科室，填写病情描述即可完成挂号，如若有未完成的同科室挂号，则不准许挂新号！）
就诊记录页面：
	查看历史就诊记录
	查看药品清单（医生开药后才可看）

医生系统（坐诊系统）
接诊房间页面：
	查看该医生科室的待诊列表（每个医生都有所属的科室，每个医生只能接诊自己所属科室的病人）
	完成就诊（输入医嘱，开药）
就诊记录页面：
	查看历史就诊记录
	查看药品清单

ps：医生坐诊只能看自己科室下的患者


# 使用方法

 请先确定已经在本地配有mysql数据库并连接上hospital数据。我们在开发时使用可视化
 工具DBeaver连接（推荐使用），也可以使用命令行连接。
 
 项目运行方式为：在"python django\源码\hospital"路径下通过命令行输入 python/python3 manage.py runserver 
 若出现以下文字则表明项目成功运行

 ###
  Watching for file changes with StatReloader
  Performing system checks...

  System check identified no issues (0 silenced).
  January 11, 2024 - 21:35:05
  Django version 3.2.13, using settings 'hospital.settings'
  Starting development server at http://127.0.0.1:8000/
  Quit the server with CTRL-BREAK.
  ###
  
  只需要点击所给出的网址便可进入网页界面，该网页以本地作为服务器。
  或者直接在任意浏览器输入以下网址进入界面：http://127.0.0.1:8000/login/


# 测试账号
为了便于简单使用，我们在此给出三个已经注册好的账号+密码（也可以根据自己需求重新注册）

    患者：310116199801011234 123456
    医生：310116199001011234 123456
    管理员：admin 123456

注意事项
添加患者时候性别填1或者2 1代表男 2代表女
添加医生时候科室填1儿科 2妇科  3外科 4内科
