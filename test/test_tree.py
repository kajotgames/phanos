import unittest
from unittest.mock import patch

from src.phanos import phanos_profiler
from src.phanos.tree import MethodTreeNode, ContextTree
from test import dummy_api
from test.dummy_api import dummy_func, DummyDbAccess


class TestTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        phanos_profiler.config(job="TEST", time_profile=True, request_size_profile=False, error_raised_label=False)

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
        self.assertEqual(first.parent(), root)
        self.assertEqual(root.children, [first])
        self.assertEqual(first.ctx.value, "DummyDbAccess:test_class")
        root.delete_child()
        self.assertEqual(root.children, [])
        self.assertEqual(first.parent, None)
        # method
        first = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        root.add_child(first)
        self.assertEqual(first.ctx.value, "DummyDbAccess:test_method")
        root.delete_child()
        # function
        first = MethodTreeNode(dummy_func)
        root.add_child(first)
        self.assertEqual(first.ctx.value, "dummy_api:dummy_func")
        root.delete_child()
        # descriptor
        access = DummyDbAccess()
        first = MethodTreeNode(access.__getattribute__)
        root.add_child(first)
        self.assertEqual(first.ctx.value, "object:__getattribute__")
        root.delete_child()
        # staticmethod
        first = MethodTreeNode(access.test_static)
        root.add_child(first)
        self.assertEqual(first.ctx.value, "DummyDbAccess:test_static")
        root.delete_child()

        first = MethodTreeNode(self.tearDown)
        root.add_child(first)
        self.assertEqual(first.ctx.value, "TestTree:tearDown")

    def test_clear_tree(self):
        """Check method for tree clearing"""
        root = phanos_profiler.tree.root
        _1 = MethodTreeNode(self.tearDown)
        root.add_child(_1)
        self.assertEqual(_1.ctx.value, "TestTree:tearDown")
        _1.add_child(MethodTreeNode(self.tearDown))
        _1.add_child(MethodTreeNode(self.tearDown))
        _1.add_child(MethodTreeNode(self.tearDown))
        with patch.object(ContextTree, "delete_node") as mock:
            phanos_profiler.clear()

        self.assertEqual(mock.call_count, 5)

        phanos_profiler.clear()
        # no children exist but error should not be raised
        phanos_profiler.tree.root.delete_child()

    def test_delete_from_tree(self):
        tree = ContextTree()
        node3 = MethodTreeNode()
        node3.ctx.context = "POST:x.y"
        tree.root.add_child(node3)
        node1 = MethodTreeNode()
        node1.ctx.context = "POST:x.y.z"
        node3.add_child(node1)
        node4 = MethodTreeNode()
        node4.ctx.context = "POST:x.y.z"
        node3.add_child(node4)
        node2 = MethodTreeNode()
        node2.ctx.context = "POST:x.y.q"
        node3.add_child(node2)

        tree.delete_node(node3)
        # tree structure
        self.assertEqual(node1.parent(), tree.root)
        self.assertEqual(node2.parent(), tree.root)
        self.assertEqual(node4.parent(), tree.root)
        self.assertEqual(len(tree.root.children), 3)
        self.assertIn(node1, tree.root.children)
        self.assertIn(node2, tree.root.children)
        self.assertIn(node4, tree.root.children)

        # reference deleting
        self.assertEqual(node3.children, [])
        self.assertEqual(node3.parent, None)

        tree.delete_node(node1)
        self.assertEqual(node2.parent(), tree.root)
        self.assertEqual(node4.parent(), tree.root)
        self.assertEqual(len(tree.root.children), 2)
        self.assertIn(node2, tree.root.children)
        self.assertIn(node4, tree.root.children)

        tree.delete_node(node2)
        tree.delete_node(node4)

        self.assertEqual(tree.root.children, [])
