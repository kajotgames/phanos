import asyncio
import unittest
from io import StringIO

from src.phanos import profiler
from src.phanos.publisher import StreamHandler
from test import dummy_api, common, testing_data
from test.dummy_api import app


class TestAsyncProfile(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        profiler.config(job="TEST", request_size_profile=False, error_raised_label=False)
        cls.app = app
        cls.client = cls.app.test_client()  # type: ignore[attr-defined]

    def setUp(self) -> None:
        self.output = StringIO()
        profile_handler = StreamHandler("name", self.output)
        profiler.add_handler(profile_handler)

    def tearDown(self) -> None:
        self.output.close()

    @classmethod
    def tearDownClass(cls) -> None:
        profiler.delete_handlers()
        profiler.delete_metrics(True, True)

    async def test_handling_error(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        with self.assertRaises(RuntimeError):
            await asyncio.gather(
                loop.create_task(async_access.raise_error()),
            )
        self.output.seek(0)
        methods, _, _ = common.parse_output(self.output.readlines())
        methods.sort()
        self.assertEqual(methods, ["AsyncTest:raise_error", "AsyncTest:raise_error.async_access_short"])

    async def test_await(self):
        async_access = dummy_api.AsyncTest()
        _ = await async_access.await_test()
        _ = await async_access.await_test()

        self.output.seek(0)
        methods, values, _ = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.test_await_out_methods)
        self.assertEqual(values, testing_data.test_await_out_values)

    async def test_task(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        task1 = loop.create_task(async_access.task_test())
        task2 = loop.create_task(async_access.async_access_short())
        await asyncio.wait([task1, task2])

        self.output.seek(0)
        methods, values, _ = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.test_task_out_methods)
        self.assertEqual(values, testing_data.test_task_out_values)

    async def test_mix(self):
        async_access = dummy_api.AsyncTest()
        await async_access.test_mix()
        self.output.seek(0)
        methods, values, _ = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.test_mix_out_methods)
        self.assertEqual(values, testing_data.test_mix_out_values)

    async def test_sync_in_async(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        task1 = loop.create_task(async_access.sync_in_async())
        task2 = loop.create_task(async_access.sync_in_async())
        await asyncio.wait([task1, task2])
        self.output.seek(0)
        methods, values, _ = common.parse_output(self.output.readlines())
        methods.sort()
        values.sort()
        self.assertEqual(methods, testing_data.sync_in_async_methods)
        self.assertEqual(values, testing_data.sync_in_async_values)

    async def test_task_wo_await(self):
        async_access = dummy_api.AsyncTest()
        loop = asyncio.get_event_loop()
        loop.create_task(async_access.wo_await())
        # wait for tasks to finish
        await asyncio.sleep(0.4)
        self.output.seek(0)
        methods, _, _ = common.parse_output(self.output.readlines())
        #  root method finished before nested task -> just root method in profiling output
        self.assertEqual(methods[0], "AsyncTest:wo_await")
        # nested method would be sent with next profiling, but value was measured
        self.assertEqual(profiler.time_profile.method[0], "AsyncTest:wo_await.async_access_short")
        # cleanup for next tests
        profiler.time_profile.cleanup()

    async def test_all_task_creation_possibilities(self):
        async_access = dummy_api.AsyncTest()
        await async_access.all_task_possibilities()
        self.output.seek(0)
        profiler.time_profile.cleanup()
        methods, _, _ = common.parse_output(self.output.readlines())
        methods.sort()
        _ = methods.pop(0)
        for method in methods:
            self.assertEqual(method, "AsyncTest:all_task_possibilities.async_access_short")
