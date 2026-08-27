
import os
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


SYSTEM_PROMPT = """# 角色
你是一个全能的助手，能够有逻辑的处理用户提出的问题。

1. 用户向你提问后，你需要判断是否能够直接给出回复，如果可以，直接给出回复。
2. 如果不能直接给出回复，你需要对用户提出的问题进行分析和步骤拆解。
3. 判断是否需要使用工具，比如：数学计算，文件读取，网页抓取等，然后在提供的工具列表里面找是否有这样的工具。

这是我的工具组册表:
{tools}

""".strip()
HUMAN_PROMPT = """用户问题：
{query}

参考资料：
<context>
{context}
</context>""".strip()


ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", HUMAN_PROMPT),
    ]
)


if __name__ == "__main__":
    _ = load_dotenv()

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL") or "",
        base_url=os.getenv("OPENAI_BASE_URL") or "",
        api_key=SecretStr(os.getenv("OPENAI_API_KEY") or ""),
    )

    chain = ANSWER_PROMPT | llm | StrOutputParser()


    answer = chain.invoke(
        {
            "query": "5 * 10 = ？",
            "context": "",
        }
    )

    print(answer)
