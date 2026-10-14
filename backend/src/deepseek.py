import requests
import os
import logging
from .constants import BOT_NAME, BOT_BRAND, NDPA_DISCLAIMER

class DeepSeek:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        logging.info(f"DeepSeek model set to: {self.model}")

    def generate_response(self, context: str, question: str, instruction: str | None = None,
                          max_tokens: int | None = None) -> str:
        if not instruction:
            instruction = (
                f"You are {BOT_NAME}, an intelligent clinical assistant for {BOT_BRAND}. "
                "You help patients with appointment booking, hospital services, departments, doctor availability, "
                "and general health service queries. You also assist hospital staff with clinical workflows, "
                "scheduling, reporting, ward management, laboratory orders, and billing queries. "
                "Use the provided context to answer accurately. If the context is insufficient, use your general "
                "medical knowledge to help, but always prioritize context. Be professional, empathetic, and concise. "
                "Never provide a clinical diagnosis — always direct patients to consult a qualified healthcare professional. "
                f"{NDPA_DISCLAIMER}"
            )
        if not self.model:
            logging.error("DeepSeek model name is not set. Please set DEEPSEEK_MODEL env variable.")
            return ""

        system_msg = instruction
        user_content = f"Context:\n{context}\n\nQuestion: {question}\n\nProvide the best possible answer."

        if not context or "No specific internal company documents" in context:
            user_content = f"Question: {question}\n\nAnswer the user's question to the best of your ability."

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content}
            ]
        }
        if max_tokens:
            # Backstop for the reply-length budget set by the caller; the prompt does the shaping.
            data["max_tokens"] = int(max_tokens)
        logging.info(f"Calling DeepSeek with model: {self.model}")
        try:
            response = requests.post(self.url, headers=headers, json=data, timeout=45)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                return content
            logging.error(f"DeepSeek API error: {response.status_code} {response.text}")
            return f"I'm sorry, I'm having trouble connecting right now. (Status: {response.status_code})"
        except Exception as e:
            logging.error(f"DeepSeek exception: {e}")
            return "I'm sorry, an internal error occurred while processing your request."