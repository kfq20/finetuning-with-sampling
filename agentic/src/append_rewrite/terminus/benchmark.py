"""Plain, unreferenced Qwen evaluation through the pinned Harbor Terminus-2.

One native generation per decision. No teacher, candidate pool, likelihood
selection, SFT export, or automatic generation retry. Official task/verifier
resources and deadlines remain the responsibility of Harbor's trial runner.
"""
import os
import time
from pathlib import Path

from e2b import AsyncTemplate, Template
from harbor.agents.terminus_2.terminus_2 import Terminus2, Terminus2Options
from harbor.environments.e2b import E2BEnvironment

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
    inference_profile: str = 'legacy'


class QwenBenchmarkAgent(Terminus2):
    options_model=QwenBenchmarkOptions

    def _init_llm(self,*args,**kwargs):
        if not getattr(self,'_native_backend',None):
            profile = self.options.inference_profile
            if profile == 'legacy':
                self._native_backend=PlainQwenLLM(
                    self.options.native_config,PinnedTokenizer(self.options.tokenizer_path),
                    Path(self.logs_dir)/'native-generation')
            elif profile in {'cancellable-thinking', 'cancellable-legacy'}:
                from .benchmark_llm import CancellableQwenLLM
                thinking = profile == 'cancellable-thinking'
                if thinking and not self.options.interleaved_thinking:
                    raise ValueError('Thinking benchmark requires retained reasoning history')
                self._native_backend=CancellableQwenLLM(
                    self.options.native_config,
                    PinnedTokenizer(self.options.tokenizer_path, enable_thinking=thinking),
                    Path(self.logs_dir)/'native-generation', thinking=thinking)
            else:
                raise ValueError('Unknown benchmark inference profile')
        return self._native_backend

    async def _query_llm(self,chat,prompt,original_instruction='',session=None):
        # Harbor's default blanket retry can duplicate an ambiguous paid POST.
        start=time.monotonic()
        response=await chat.chat(prompt,**self._llm_call_kwargs)
        self._api_request_times.append((time.monotonic()-start)*1000)
        return response


# Alibaba's E2B-compatible image converter requires the registry credentials
# already provisioned with this account. They stay in the controller process.
class AlibabaBenchmarkEnvironment(E2BEnvironment):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._template_name='tb21ali-v2-'+self.environment_id[:16]

    async def _create_template(self):
        if not self.task_env_config.docker_image:
            raise ValueError('Official pinned image required for this adapter')
        if not all(os.environ.get(k) for k in ['REGISTRY_USERNAME','REGISTRY_PASSWORD']):
            raise ValueError('Controller registry credentials missing')
        if '.cr.aliyuncs.com/' not in self.task_env_config.docker_image or '@sha256:' not in self.task_env_config.docker_image:
            raise ValueError('Mirror official image to ACR by digest before using ACR credentials')
        template=Template().from_image(
            self.task_env_config.docker_image,username=os.environ['REGISTRY_USERNAME'],
            password=os.environ['REGISTRY_PASSWORD'])
        kwargs={}
        if self._effective_cpus is not None:kwargs['cpu_count']=self._effective_cpus
        if self._effective_memory_mb is not None:kwargs['memory_mb']=self._effective_memory_mb
        # One build only: this provider rejects rebuilding a CREATE_FAILED ID.
        await AsyncTemplate.build(template=template,alias=self._template_name,**kwargs)
