import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from orjson import orjson

import testing_data
from phanos.messaging import BlockingPublisher, AsyncioPublisher


class TestBasePublisher(unittest.TestCase):
    def setUp(self):
        self.publisher = BlockingPublisher()

    def tearDown(self):
        self.publisher = None

    def test_init(self):
        publisher = BlockingPublisher(retry=-1)
        self.assertEqual(publisher.retry, 0)
        self.assertIsNone(publisher.connection)
        self.assertIsNone(publisher.channel)
        self.assertEqual(publisher.exchange_name, "profiling")
        self.assertEqual(publisher.exchange_type, "fanout")
        self.assertIsNotNone(publisher.connection_parameters)

    def test_is_bound(self):
        with self.subTest("No channel"):
            self.assertFalse(self.publisher._is_bound())
        self.publisher.channel = MagicMock()
        self.publisher.channel.is_closed = False
        with self.subTest("Channel is open"):
            self.assertTrue(self.publisher._is_bound())

    def test_is_connected(self):
        with self.subTest("No connection"):
            self.assertFalse(self.publisher.is_connected())
        self.publisher.connection = MagicMock()
        self.publisher.connection.is_closed = False
        with self.subTest("Connection is open"):
            self.assertTrue(self.publisher.is_connected())

    def test_bool(self):
        with self.subTest("No connection and channel"):
            self.assertFalse(self.publisher)

        mock_false = MagicMock()
        mock_false.return_value = True
        self.publisher.is_connected = self.publisher._is_bound = mock_false
        self.publisher.connection = self.publisher.channel = MagicMock()
        with self.subTest("Connection and channel are open"):
            self.assertTrue(self.publisher)


class TestBlockingPublisher(unittest.TestCase):
    @patch("phanos.messaging.BlockingPublisher._is_bound")
    @patch("phanos.messaging.BlockingPublisher.is_connected")
    def test_close(
        self,
        mock_is_connected: MagicMock,
        mock_is_bound: MagicMock,
    ):
        publisher = BlockingPublisher()
        mock_connection = publisher.connection = MagicMock()
        mock_channel = publisher.channel = MagicMock()
        mock_is_connected.return_value = mock_is_bound.return_values = True
        with self.subTest("Both close"):
            publisher.close()
            mock_channel.close.assert_called_once()
            mock_connection.close.assert_called_once()
            self.assertIsNone(publisher.connection)
            self.assertIsNone(publisher.channel)

        mock_is_connected.return_value = False
        publisher.connection = mock_connection
        publisher.channel = mock_channel
        mock_connection.reset_mock()
        mock_channel.reset_mock()
        with self.subTest("No close"):
            publisher.close()
            mock_channel.close.assert_not_called()
            mock_connection.close.assert_not_called()
            self.assertIsNone(publisher.connection)
            self.assertIsNone(publisher.channel)

    @patch("phanos.messaging.BlockingConnection")
    def test_connect(self, mock_connection: MagicMock):
        publisher = BlockingPublisher()
        publisher.connect()
        mock_connection.assert_called_once()
        mock_connection.return_value.channel.assert_called_once()
        mock_connection.return_value.channel.return_value.exchange_declare.assert_called_once()

    @patch("phanos.messaging.BlockingPublisher.close")
    @patch("phanos.messaging.BlockingPublisher.connect")
    def test_reconnect(self, mock_connect: MagicMock, mock_close: MagicMock):
        publisher = BlockingPublisher()
        with self.subTest("reconnect"):
            publisher.reconnect()
            mock_close.assert_called_once()
            mock_connect.assert_called_once()

        mock_connect.side_effect = ConnectionError()
        with self.subTest("reconnect with error"):
            with self.assertRaises(ConnectionError):
                publisher.reconnect()
        with self.subTest("silent"):
            publisher.reconnect(True)

    @patch("phanos.messaging.BlockingPublisher.reconnect")
    @patch("phanos.messaging.BasePublisher.__bool__")
    def test_check_or_rebound(self, mock_bool: MagicMock, mock_reconnect: MagicMock):
        mock_bool.return_value = False
        publisher = BlockingPublisher()
        with self.subTest("reconnect"):
            publisher.check_or_rebound()
            mock_reconnect.assert_called_once()

        mock_reconnect.reset_mock()
        mock_bool.return_value = True
        with self.subTest("no reconnect"):
            publisher.check_or_rebound()
            mock_reconnect.assert_not_called()

    @patch("phanos.messaging.BlockingPublisher.check_or_rebound")
    @patch("phanos.messaging.BlockingPublisher.reconnect")
    def test_publish(self, mock_reconnect: MagicMock, mock_check_or_rebound: MagicMock):
        publisher = BlockingPublisher()
        publisher.channel = MagicMock()
        with self.subTest("no records"):
            self.assertTrue(publisher.publish([]))
            publisher.channel.basic_publish.assert_not_called()

        with self.subTest("publish"):
            self.assertTrue(publisher.publish([testing_data.test_handler_in]))
            publisher.channel.basic_publish.assert_called_once_with(
                exchange=publisher.exchange_name,
                body=orjson.dumps([testing_data.test_handler_in]),
                routing_key=testing_data.test_handler_in["job"],
            )
            mock_check_or_rebound.assert_called_once()

        publisher.channel.reset_mock()
        publisher.channel.basic_publish.side_effect = ConnectionError()
        publisher.connection_parameters.retry_delay = 0
        publisher.retry = 2
        with self.subTest("reconnect"):
            self.assertFalse(publisher.publish([testing_data.test_handler_in]))
            self.assertEqual(publisher.channel.basic_publish.call_count, 2 + 1)
            self.assertEqual(mock_reconnect.call_count, 2 + 1)


class TestAsyncPublisher(unittest.IsolatedAsyncioTestCase):
    @patch("phanos.messaging.AsyncioPublisher._is_bound")
    @patch("phanos.messaging.AsyncioPublisher.is_connected")
    async def test_close(self, mock_is_connected: MagicMock, mock_is_bound: MagicMock):
        publisher = AsyncioPublisher()
        mock_connection = publisher.connection = AsyncMock()
        mock_channel = publisher.channel = AsyncMock()
        mock_is_connected.return_value = mock_is_bound.return_values = True
        with self.subTest("Both close"):
            await publisher.close()
            mock_channel.close.assert_awaited_once()
            mock_connection.close.assert_awaited_once()
            self.assertIsNone(publisher.connection)
            self.assertIsNone(publisher.channel)

        mock_is_connected.return_value = False
        publisher.connection = mock_connection
        publisher.channel = mock_channel
        mock_connection.reset_mock()
        mock_channel.reset_mock()
        with self.subTest("No close"):
            await publisher.close()
            mock_channel.close.assert_not_awaited()
            mock_connection.close.assert_not_awaited()
            self.assertIsNone(publisher.connection)
            self.assertIsNone(publisher.channel)

    @patch("phanos.messaging.aio_pika.connect_robust")
    async def test_connect(self, mock_connect: AsyncMock):
        publisher = AsyncioPublisher()

        await publisher.connect()
        mock_connect.assert_called_once()
        mock_connect.return_value.channel.assert_called_once()
        mock_connect.return_value.channel.return_value.declare_exchange.assert_called_once()
        self.assertIsNotNone(publisher.connection)
        self.assertIsNotNone(publisher.channel)
        self.assertIsNotNone(publisher.exchange)

    @patch("phanos.messaging.AsyncioPublisher.close")
    @patch("phanos.messaging.AsyncioPublisher.connect")
    async def test_reconnect(self, mock_connect: AsyncMock, mock_close: AsyncMock):
        publisher = AsyncioPublisher()
        with self.subTest("reconnect"):
            await publisher.reconnect()
            mock_close.assert_awaited_once()
            mock_connect.assert_awaited_once()

        mock_connect.side_effect = ConnectionError()
        with self.subTest("reconnect with error"):
            with self.assertRaises(ConnectionError):
                await publisher.reconnect()
        with self.subTest("silent"):
            await publisher.reconnect(True)

    @patch("phanos.publisher.AsyncioPublisher.reconnect")
    @patch("phanos.messaging.BasePublisher.__bool__")
    async def test_check_or_rebound(self, mock_bool: MagicMock, mock_reconnect: MagicMock):
        mock_bool.return_value = False
        publisher = AsyncioPublisher()
        with self.subTest("reconnect"):
            await publisher.check_or_rebound()
            mock_reconnect.assert_called_once()

        mock_reconnect.reset_mock()
        mock_bool.return_value = True
        with self.subTest("no reconnect"):
            await publisher.check_or_rebound()
            mock_reconnect.assert_not_called()

    @patch("phanos.messaging.AsyncioPublisher.check_or_rebound")
    @patch("phanos.messaging.AsyncioPublisher.reconnect")
    async def test_publish(self, mock_reconnect: AsyncMock, mock_check_or_rebound: AsyncMock):
        publisher = AsyncioPublisher()
        publisher.exchange = AsyncMock()
        with self.subTest("no records"):
            self.assertTrue(await publisher.publish([]))
            publisher.exchange.publish.assert_not_awaited()

        with self.subTest("publish"):
            self.assertTrue(await publisher.publish([testing_data.test_handler_in]))
            publisher.exchange.publish.assert_awaited_once()
            mock_check_or_rebound.assert_called_once()

        publisher.exchange.reset_mock()
        publisher.exchange.publish.side_effect = ConnectionError()
        publisher.connection_parameters.retry_delay = 0
        publisher.retry = 2
        with self.subTest("reconnect"):
            self.assertFalse(await publisher.publish([testing_data.test_handler_in]))
            self.assertEqual(publisher.exchange.publish.call_count, 2 + 1)
            self.assertEqual(mock_reconnect.call_count, 2 + 1)
