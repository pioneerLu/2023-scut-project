
import openai

# 设置OpenAI API密钥
def chaxun(content):
    openai.api_key = "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"
# 输入问题，并进行简单的文字处理
    question =content+"，应该去医院挂什么科，不要向我解释原因。"

    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=question,
        max_tokens=300,  # 控制回答的长度
        n=1,  # 生成一个回答
        stop="。"
    )
# 提取回答
    answer = response.choices[0].text.strip()
    return answer

