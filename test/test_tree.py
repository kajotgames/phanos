import unittest
from io import StringIO
from unittest.mock import patch

import phanos
from phanos import phanos_profiler
from phanos.handlers import StreamHandler
from phanos.tree import MethodTreeNode
from test import dummy_api, testing_data
from test.dummy_api import dummy_method, DummyDbAccess


class TestTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST", time_profile=True, request_size_profile=False)

    @classmethod
    def tearDownClass(cls) -> None:
        phanos_profiler.delete_handlers()
        phanos_profiler.delete_metrics(True, True)

    def tearDown(self) -> None:
        pass

    def test_simple_context(self):
        """checks if context is created correctly for all kinds of methods/functions"""
        root = MethodTreeNode()
        # classmethod
        first = MethodTreeNode(dummy_api.DummyDbAccess.test_class)
        root.add_child(first)
        self.assertEqual(first.parent, root)
        self.assertEqual(root.children, [first])
        self.assertEqual(first.ctx.context, "DummyDbAccess:test_class")
        root.delete_child()
        self.assertEqual(root.children, [])
        self.assertEqual(first.parent, None)
        # method
        first = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        root.add_child(first)
        self.assertEqual(first.ctx.context, "DummyDbAccess:test_method")
        root.delete_child()
        # function
        first = MethodTreeNode(dummy_method)
        root.add_child(first)
        self.assertEqual(first.ctx.context, "dummy_api:dummy_method")
        root.delete_child()
        # descriptor
        access = DummyDbAccess()
        first = MethodTreeNode(access.__getattribute__)
        root.add_child(first)
        self.assertEqual(first.ctx.context, "object:__getattribute__")
        root.delete_child()
        # staticmethod
        first = MethodTreeNode(access.test_static)
        root.add_child(first)
        self.assertEqual(first.ctx.context, "DummyDbAccess:test_static")
        root.delete_child()

        first = MethodTreeNode(self.tearDown)
        root.add_child(first)
        self.assertEqual(first.ctx.context, "TestTree:tearDown")

    def test_clear_tree(self):
        """Check method for tree clearing"""
        root = phanos_profiler.tree.root
        _1 = MethodTreeNode(self.tearDown)
        root.add_child(_1)
        self.assertEqual(_1.ctx.context, "TestTree:tearDown")
        _1.add_child(MethodTreeNode(self.tearDown))
        _1.add_child(MethodTreeNode(self.tearDown))
        _1.add_child(MethodTreeNode(self.tearDown))
        with patch.object(MethodTreeNode, "clear_children") as mock:
            phanos_profiler.clear()

        mock.assert_any_call()
        self.assertEqual(mock.call_count, 5)

        phanos_profiler.clear()
        # no children exist but error should not be raised
        phanos_profiler.tree.root.delete_child()

    def test_delete_from_tree(self):
        """test deleting from tree"""
        tree = phanos.tree.ContextTree()
        node1 = MethodTreeNode()
        node1.ctx.context = "POST:x.y.z"
        tree.insert(node1)
        node2 = MethodTreeNode()
        node2.ctx.context = "POST:x.y.q"
        tree.insert(node2)
        node3 = MethodTreeNode()
        node3.ctx.context = "POST:x.y"
        tree.insert(node3)
        node4 = MethodTreeNode()
        node4.ctx.context = "POST:x.y.z"
        tree.insert(node4)

        tree.delete_node(node3)
        # tree structure
        self.assertEqual(node1.parent, tree.root)
        self.assertEqual(node2.parent, tree.root)
        self.assertEqual(node4.parent, tree.root)
        self.assertEqual(len(tree.root.children), 3)
        self.assertIn(node1, tree.root.children)
        self.assertIn(node2, tree.root.children)
        self.assertIn(node4, tree.root.children)

        # reference deleting
        self.assertEqual(node3.children, [])
        self.assertEqual(node3.parent, None)

        tree.delete_node(node1)
        self.assertEqual(node2.parent, tree.root)
        self.assertEqual(node4.parent, tree.root)
        self.assertEqual(len(tree.root.children), 2)
        self.assertIn(node2, tree.root.children)
        self.assertIn(node4, tree.root.children)

        tree.delete_node(node2)
        tree.delete_node(node4)

        self.assertEqual(tree.root.children, [])

    def test_insert_into_tree(self):
        """test insertion into tree"""
        tree = phanos.tree.ContextTree()

        node1 = MethodTreeNode()
        node1.ctx.context = "POST:x.y.z"
        tree.insert(node1)
        self.assertIn(node1, tree.root.children)
        self.assertEqual(node1.parent, tree.root)

        node2 = MethodTreeNode()
        node2.ctx.context = "POST:x.y.q"
        tree.insert(node2)
        self.assertIn(node2, tree.root.children)
        self.assertEqual(node2.parent, tree.root)
        self.assertEqual(len(tree.root.children), 2)

        node3 = MethodTreeNode()
        node3.ctx.context = "POST:x.y"
        tree.insert(node3)
        self.assertIn(node3, tree.root.children)
        self.assertEqual(len(tree.root.children), 1)
        self.assertEqual(node3.parent, tree.root)
        self.assertEqual(node1.parent, node3)
        self.assertEqual(node2.parent, node3)

        node4 = MethodTreeNode()
        node4.ctx.context = "POST:x.y.z"
        tree.insert(node4)
        self.assertEqual(node4.parent, node3)
        self.assertEqual(node4.children, [])
        self.assertEqual(len(node3.children), 3)
