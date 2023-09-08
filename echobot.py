"""

Sample bot that echoes back messages.

This is the simplest possible bot and a great place to start if you want to build your own bot.

"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from typing import AsyncIterable

import openai
import pdftotext
import pytesseract
import requests

from fastapi_poe import PoeBot, run
from fastapi_poe.types import QueryRequest
from PIL import Image
from sse_starlette.sse import ServerSentEvent

assert openai.api_key

print("version", pytesseract.get_tesseract_version())

SETTINGS = {
    "report_feedback": True,
    "context_clear_window_secs": 60 * 60,
    "allow_user_context_clear": True,
}

conversation_cache = defaultdict(
    lambda: [{"role": "system", "content": RESUME_SYSTEM_PROMPT}]
)

url_cache = {}


async def parse_image_document_from_url(image_url: str) -> tuple[bool, str]:
    try:
        response = requests.get(image_url.strip())
        img = Image.open(BytesIO(response.content))

        custom_config = "--psm 4"
        text = pytesseract.image_to_string(img, config=custom_config)
        text = text[:2000]
        return True, text
    except BaseException:
        return False, ""


async def parse_pdf_document_from_url(pdf_url: str) -> tuple[bool, str]:
    try:
        response = requests.get(pdf_url)
        with BytesIO(response.content) as f:
            pdf = pdftotext.PDF(f)
        text = "\n\n".join(pdf)
        text = text[:2000]
        return True, text
    except requests.exceptions.MissingSchema:
        return False, ""
    except BaseException:
        return False, ""


UPDATE_IMAGE_PARSING = """\
I am parsing your resume with Tesseract OCR ...

---

"""

# TODO: show an image, if Markdown support for that happens before image upload
UPDATE_LLM_QUERY = """\
I have received your resume.

{resume}

I am querying the language model for analysis ...

---

"""

MULTIWORD_FAILURE_REPLY = """\
Please only send a URL.
Do not include any other words in your reply.

These are examples of resume the bot can accept.

https://raw.githubusercontent.com/jakegut/resume/master/resume.png

https://pjreddie.com/static/Redmon%20Resume.pdf

https://i.imgur.com/XYyvW6B.png

https://media.discordapp.net/attachments/1070915874996895744/1070915875139506296/jake.jpg

See https://poe.com/huikang/1512927999933968 for an example of an interaction.

You can also try https://poe.com/xyzFormatter for advice specifically on your bullet points.
"""

PARSE_FAILURE_REPLY = """
I could not load your resume.
Please check whether the link is publicly accessible.

---

If you are uploading to Github, please ensure that you are sending something like

https://raw.githubusercontent.com/jakegut/resume/master/resume.png

rather than

https://github.com/jakegut/resume/blob/master/resume.png

To get to raw.githubusercontent.com from github.com, right click "Download" and "Copy link address".

---

If you are uploading to imgur, please ensure that you are sending something like

https://i.imgur.com/XYyvW6B.png

rather than

https://imgur.com/a/6AeB8Vy

To get i.imgur.com from imgur.com, right click the image and "Copy image address".

---

This bot is not able to accept links from Google drive.

Remember to redact sensitive information, especially contact details.
"""


# flake8: noqa: E501

RESUME_SYSTEM_PROMPT = """
You will be given text from a resume, extracted with Optical Character Recognition.
You will suggest specific improvements for a resume, by the standards of US/Canada software industry.

Do not give generic comments.
All comments has to quote the relevant sentence in the resume where there is an issue.

You will only check the resume text for formatting errors, and suggest improvements to the bullet points.
You will not evaluate the resume, as your role is to suggest improvements.
You will focus on your comments related to tech and engineering content.
Avoid commenting on extra-curricular activities.


The following are the formmatting errors to check.
If there is a formatting error, quote the original text, and suggest how should it be rewritten.
Only raise these errors if you are confident that this is an error.

- Inconsistent date formats. Prefer Mmm YYYY for date formats.
- Misuse of capitalization. Do not capitalize words that are not capitalized in professional communication.
- Misspelling of technical terminologies. (Ignore if the error is likely to due OCR parsing inaccuracies.)
- The candidate should not explictly label their level of proficiency in the skills section.


Suggest improvements to bullet points according to these standards.
Quote the original text (always), and suggest how should it be rewritten.

- Emulate the Google XYZ formula - e.g. Accomplished X, as measured by Y, by doing Z
- Ensure the bullet points are specific.
  It shows exactly what feature or system the applicant worked on, and their exact contribution.
- Specify the exact method or discovery where possible.
- Ensure the metrics presented by the resume can be objectively measured.
  Do not use unmeasurable metrics like “effectiveness” or “efficiency”.
- You may assume numbers of the metrics in your recommendations.
- You may assume additional facts not mentioned in the bullet points in your recommendations.
- Prefer simpler sentence structures and active language
    - Instead of "Spearheaded development ...", write "Developed ..."
    - Instead of "Utilized Python to increase the performance of ...", write "Increased the performance of ... with Python"

Please suggest only the most important improvements to the resume. All your suggestions should quote from the resume.
Each suggestion should start with "Suggestion X" (e.g. Suggestion 1), and followed by two new lines.
In the suggestion, quote from the resume, and write what you suggest to improve.
At the end of each suggestion, add a markdown horizontal rule, which is `---`.
Do not reproduce the full resume unless asked. You will not evaluate the resume, as your role is to suggest improvements.
"""

RESUME_STARTING_PROMPT = """
The resume is contained within the following triple backticks

```
{}
```
"""


def process_message_with_gpt(message_history: list[dict[str, str]]) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo", messages=message_history, temperature=0.1
    )
    bot_statement = response["choices"][0]["message"]["content"]
    return bot_statement


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        user_statement: str = query.query[-1].content
        print(query.conversation_id, user_statement)

        if query.conversation_id not in url_cache:
            # TODO: validate user_statement is not malicious
            if len(user_statement.strip().split()) > 1:
                yield self.text_event(MULTIWORD_FAILURE_REPLY)
                return

            content_url = user_statement.strip()
            content_url = content_url.split("?")[0]  # remove query_params

            yield self.text_event(UPDATE_IMAGE_PARSING)

            if content_url.endswith(".pdf"):
                print("parsing pdf", content_url)
                success, resume_string = await parse_pdf_document_from_url(content_url)
            else:  # assume image
                print("parsing image", content_url)
                success, resume_string = await parse_image_document_from_url(
                    content_url
                )

            if not success:
                yield self.text_event(PARSE_FAILURE_REPLY)
                return
            yield self.text_event(UPDATE_LLM_QUERY.format(resume=content_url))
            url_cache[query.conversation_id] = content_url
            user_statement = RESUME_STARTING_PROMPT.format(resume_string)

        conversation_cache[query.conversation_id].append(
            {"role": "user", "content": user_statement}
        )

        message_history = conversation_cache[query.conversation_id]
        bot_statement = process_message_with_gpt(message_history)
        bot_statement = bot_statement.replace("---", "\n---\n")
        yield self.text_event(bot_statement)

        conversation_cache[query.conversation_id].append(
            {"role": "assistant", "content": bot_statement}
        )


if __name__ == "__main__":
    run(EchoBot())