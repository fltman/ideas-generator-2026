import os
from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def send_openai_request(prompt, system_prompt=None, openai_api_key=None, openai_model=None, raw_response=False):
    try:
        api_key = openai_api_key or os.environ.get("OPENROUTER_API_KEY")
        client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request_params = {
            "model": openai_model,
            "messages": messages,
            "extra_headers": {
                "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "http://localhost"),
                "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "IdeaSphere Kronoberg"),
            },
        }

        if not raw_response:
            request_params["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**request_params)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in OpenRouter request: {str(e)}")
        raise e
