import functions_framework
import os

from flask import abort

from linebot import (
  LineBotApi, WebhookHandler
)
from linebot.exceptions import (
  InvalidSignatureError
)
from linebot.models import (
  MessageEvent, TextMessage, TextSendMessage
)

from langchain.agents import (
  AgentType, load_tools, initialize_agent
)
from langchain.chat_models import ChatOpenAI
from langchain.agents.chat.prompt import SUFFIX

line_bot_api = LineBotApi(os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)

# set search tool name. "google-serper", "google-search", etc.
search_tool = 'google-serper'

tools = load_tools([search_tool, 'llm-math'], llm=llm)

suffix = SUFFIX + """
Answer should be in Japanese. Include as much information as possible \
to support your answer.
"""

agent = initialize_agent(tools=tools,
                         llm=llm,
                         agent=AgentType.CHAT_ZERO_SHOT_REACT_DESCRIPTION,
                         agent_kwargs=dict(suffix=suffix),
                         verbose=True)

@functions_framework.http
def main(request):
  """HTTP Cloud Function.
  Args:
    request (flask.Request): The request object.
    <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
  Returns:
    The response text, or any set of values that can be turned into a
    Response object using `make_response`
    <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
  """
  signature = request.headers['X-Line-Signature']

  body = request.get_data(as_text=True)

  try:
    handler.handle(body, signature)
  except InvalidSignatureError:
    print("Invalid signature. Please check your channel access token/channel secret.")
    abort(400)
 
  return 'OK'
  
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
  try:
    response = agent.run(input=event.message.text)
  except Exception as e:
    response = str(e)
    print(response)
    if not response.startswith("Could not parse LLM output: "):
      response = '大変申し訳ありません。エラーが発生したため、回答できません。'
    else:
      # 回答が得られているが、Parse Errorになる場合のアドホックな対応
      response = response[len("Could not parse LLM output: "):]
    
  line_bot_api.reply_message(
    event.reply_token,
    TextSendMessage(text=response))
