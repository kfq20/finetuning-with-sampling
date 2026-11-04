"""Plain, unreferenced Qwen evaluation through the pinned Harbor Terminus-2.

One native generation per decision. No teacher, candidate pool, likelihood
selection, SFT export, or automatic generation retry. Official task/verifier
resources and deadlines remain the responsibility of Harbor's trial runner.
"""
import time
from pathlib import Path

from harbor.agents.terminus_2.terminus_2 import Terminus2, Terminus2Options

from .episode import EpisodeLLM
from .tokenizer import PinnedTokenizer


class PlainQwenLLM(EpisodeLLM):
    def __init__(self,config,tokenizer,root):
        super().__init__(config,tokenizer,root,reference=None,stream=True)

    def get_model_context_limit(self):
        return self.client.config['context_limit']


class QwenBenchmarkOptions(Terminus2Options):
    native_config: str
    tokenizer_path: str


class QwenBenchmarkAgent(Terminus2):
    options_model=QwenBenchmarkOptions

    def _init_llm(self,*args,**kwargs):
        if not getattr(self,'_native_backend',None):
            self._native_backend=PlainQwenLLM(
                self.options.native_config,PinnedTokenizer(self.options.tokenizer_path),
                Path(self.logs_dir)/'native-generation')
        return self._native_backend

    async def _query_llm(self,chat,prompt,original_instruction='',session=None):
        # Harbor's default blanket retry can duplicate an ambiguous paid POST.
        start=time.monotonic()
        response=await chat.chat(prompt,**self._llm_call_kwargs)
        self._api_request_times.append((time.monotonic()-start)*1000)
        return response
