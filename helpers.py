import os

from flask import redirect, session
from openai import OpenAI
from functools import wraps

# Initialize OpenAI client
client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def logout_required(f):
    """
    Decorate routes to require logout.

     https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
     """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is not None:
            return redirect("chat/history")
        return f(*args, **kwargs)

    return decorated_function


def model_call(system_prompt,  user_prompt, api_model="openai/gpt-oss-120b", return_type="string", history = "empty"):
    """
    Make the call to the LLM.
    default model = openai/gpt-oss-120b
    default return_type = strings

    """
    if return_type == "string":
        response = client.chat.completions.create(
                    model= api_model,
                    messages=[
                        {"role": "system", "content": system_prompt}, + history +
                        {"role": "user", "content": user_prompt}
                    ]
                )

        return response

    else:
        response = client.chat.completions.create(
                    model= api_model,
                    response_format={"type": "json_object"}, # Returns a JSON
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )

        return response
