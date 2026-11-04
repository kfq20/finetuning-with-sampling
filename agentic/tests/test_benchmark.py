import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,AsyncMock

try:
    from append_rewrite.terminus.benchmark import PlainQwenLLM,AlibabaBenchmarkEnvironment
    AVAILABLE=True
except ImportError:AVAILABLE=False


@unittest.skipUnless(AVAILABLE,'Optional Harbor/E2B dependencies')
class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_baseline_generates_once_without_reference_or_scoring(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cfg=root/'config.json';cfg.write_text(json.dumps({'native_endpoint':'http://127.0.0.1:18131/generate','base_url':'http://127.0.0.1:18131','model_id':'Qwen/Qwen3.8-27B','api_key':'local','context_limit':262144}));cfg.chmod(0o600)
            class Tokenizer:
                def apply_chat_template(self,messages,**kwargs):return json.dumps(messages)
            llm=PlainQwenLLM(cfg,Tokenizer(),root/'native')
            response={'text':'{"analysis":"done","plan":"done","commands":[],"task_complete":true}','meta_info':{'prompt_tokens':10,'completion_tokens':5,'cached_tokens':0,'id':'test'}}
            with patch.object(llm.client,'generate',return_value=response) as generate,patch.object(llm.client,'score',side_effect=AssertionError('scoring forbidden')):
                result=await llm.call('task')
            self.assertEqual(result.content,response['text']);generate.assert_called_once()
            self.assertNotIn('expert_reference',generate.call_args.args[0]);self.assertEqual(llm.get_model_context_limit(),262144)

    async def test_registry_auth_and_resources_passed_only_to_builder(self):
        env=object.__new__(AlibabaBenchmarkEnvironment);env.task_env_config=SimpleNamespace(docker_image='example.cr.aliyuncs.com/test/image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');env._template_name='test'
        with patch.dict('os.environ',{'REGISTRY_USERNAME':'registry-user','REGISTRY_PASSWORD':'registry-test-secret'},clear=True),patch('append_rewrite.terminus.benchmark.Template') as template,patch('append_rewrite.terminus.benchmark.AsyncTemplate.build',new_callable=AsyncMock) as build,patch.object(AlibabaBenchmarkEnvironment,'_effective_cpus',1),patch.object(AlibabaBenchmarkEnvironment,'_effective_memory_mb',2048):
            await env._create_template()
            template.return_value.from_image.assert_called_once_with('example.cr.aliyuncs.com/test/image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',username='registry-user',password='registry-test-secret')
            self.assertEqual(build.await_args.kwargs['cpu_count'],1);self.assertEqual(build.await_args.kwargs['memory_mb'],2048)

    async def test_failed_build_is_not_retried(self):
        env=object.__new__(AlibabaBenchmarkEnvironment);env.task_env_config=SimpleNamespace(docker_image='example.cr.aliyuncs.com/test/image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');env._template_name='test'
        with patch.dict('os.environ',{'REGISTRY_USERNAME':'user','REGISTRY_PASSWORD':'secret'},clear=True),patch('append_rewrite.terminus.benchmark.Template'),patch('append_rewrite.terminus.benchmark.AsyncTemplate.build',new_callable=AsyncMock,side_effect=RuntimeError('build failure')) as build,patch.object(AlibabaBenchmarkEnvironment,'_effective_cpus',1),patch.object(AlibabaBenchmarkEnvironment,'_effective_memory_mb',2048):
            with self.assertRaises(RuntimeError):await env._create_template()
            self.assertEqual(build.await_count,1)
