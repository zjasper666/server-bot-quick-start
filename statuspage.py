from datetime import datetime
import requests
import os
import fastapi_poe.client as fp_client
import fastapi_poe.types as fp_types
import asyncio


async def get_bot_response(bot_name, messages):
    response = ""
    async for partial in fp_client.get_bot_response(messages=messages,
                                             bot_name=bot_name,
                                             api_key=os.environ["POE_API_KEY"]):
        response += partial.text
    return response


def get_utc_timestring():
    
    current_utc_time = datetime.utcnow()
    formatted_time = current_utc_time.strftime('%Y-%m-%d %H:%M:%S')
    
    return formatted_time



def get_components():
    page_id = os.environ["STATUSPAGE_PAGE_ID"]
    api_key = os.environ["STATUSPAGE_API_KEY"]
    url = f"https://api.statuspage.io/v1/pages/{page_id}/components/"

    headers = {
        "Authorization": f"OAuth {api_key}",
    }
    
    response = requests.get(url, headers=headers)
    
    return response


def update_component(component_id, description, status):
    page_id = os.environ["STATUSPAGE_PAGE_ID"]
    api_key = os.environ["STATUSPAGE_API_KEY"]
    url = f"https://api.statuspage.io/v1/pages/{page_id}/components/{component_id}"
    
    headers = {
        "Authorization": f"OAuth {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "component": {
            "description": description,
            "status": status,
        }
    }
    
    response = requests.patch(url, headers=headers, json=payload)
    
    return response



def test_bot(bot_name, user_message, expected_reply_substring):
    component_id = BOT_NAME_TO_COMPONENT_ID[bot_name]

    print(f"Testing {bot_name}")

    messages = [fp_types.ProtocolMessage(role="user", content=user_message)]
    response = None

    try:
        response = asyncio.run(get_bot_response(bot_name, messages))
        print(f"Response:\n{response}")
    except Exception as e:
        print(str(e))


    if response is None:
        description = f"Did not receive response at {get_utc_timestring()} UTC"
        status = "major_outage"

    elif expected_reply_substring in response:
        description = f"Expected response received at {get_utc_timestring()} UTC"
        status = "operational"

    else:
        description = f"Response did not contain expected substring at {get_utc_timestring()} UTC"
        status = "degraded_performance"


    print(f"Description: {description}")
    print(f"Status: {status}")
    print()

    update_component(component_id, description, status)        


BOT_NAME_TO_COMPONENT_ID = {}
for component in get_components().json():
    BOT_NAME_TO_COMPONENT_ID[component["name"]] = component["id"]

test_bot(
    bot_name = "EchoBotDemonstration",
    user_message = "hello there",
    expected_reply_substring = "hello there",
)

test_bot(
    bot_name = "ChatGPT",
    user_message = "What is 1+2?",
    expected_reply_substring = "3",
)

test_bot(
    bot_name = "AllCapsBotDemo",
    user_message = "Who is the 1st US President?",
    expected_reply_substring = "WASHINGTON",
)

test_bot(
    bot_name = "PythonAgent",
    user_message = "make scatter plot",
    expected_reply_substring = "![",
)

test_bot(
    bot_name = "GPT-4-128k-mirror",
    user_message = "What is 1+2",
    expected_reply_substring = "3",
)