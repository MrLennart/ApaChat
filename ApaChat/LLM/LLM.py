from openai import OpenAI
class LLM:
    def __init__(self, base_url:str=None, model_name:str=None, api_key:str=None):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model_name
        self.tools = []

    def chat_completion(self, messages:list[str], temperature:int=0, n:int=1, max_tokens:int=2000):
        if self.model:
            try:
                kwargs = dict(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    n=n,
                    max_tokens=max_tokens
                )
                if self.tools:  # Only add tools if not empty
                    kwargs["tools"] = self.tools
                response = self.client.chat.completions.create(**kwargs)
                return response
            except Exception as e:
                raise RuntimeError(f"An error occurred during chat completion: {str(e)}")
        else:
            raise ValueError("Model name is not set. Please provide a valid model name.")

    def list_models(self):
        """
        Lists available models from the OpenAI API.
        """
        try:
            response = self.client.models.list()
            return response.data
        except Exception as e:
            raise RuntimeError(f"An error occurred while listing models: {str(e)}")

def available_LLM_providers():
    """
    Returns a list of available LLM providers.
    """
    return {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1"
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1"
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1"
    },
    "fireworks": {
        "name": "Fireworks.ai",
        "base_url": "https://api.fireworks.ai/inference/v1"
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1"
    }
}

