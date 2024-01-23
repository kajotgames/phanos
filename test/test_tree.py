import sys
import unittest
import weakref
from unittest.mock import patch, MagicMock

from phanos import tree
from src.phanos import phanos_profiler
from src.phanos.tree import MethodTreeNode, ContextTree
from test import dummy_api


class TestContext(unittest.TestCase):
    def test_init(self):
        ctx = tree.Context(dummy_api.DummyDbAccess.test_method)
        self.assertEqual(ctx.value, "test_method")
        self.assertEqual(ctx.method, dummy_api.DummyDbAccess.test_method)
        self.assertEqual(ctx.top_module, "test")

    def test_str_and_repr(self):
        ctx = tree.Context(dummy_api.DummyDbAccess.test_method)
        self.assertEqual(str(ctx), "test_method")
        self.assertEqual(repr(ctx), "test_method")

        ctx = tree.Context()
        self.assertEqual(str(ctx), "")
        self.assertEqual(repr(ctx), "")

    def test_prepend_method_class(self):
        with self.subTest("METHOD FROM CLASS"):
            ctx = tree.Context(dummy_api.DummyDbAccess.test_method)
            ctx.prepend_method_class()
            self.assertEqual(ctx.value, "DummyDbAccess:test_method")

        with self.subTest("METHOD FROM CLASS INSTANCE"):
            ctx = tree.Context(dummy_api.DummyDbAccess().test_method)
            ctx.prepend_method_class()
            self.assertEqual(ctx.value, "DummyDbAccess:test_method")

        with self.subTest("CLASSMETHOD"):
            ctx = tree.Context(dummy_api.DummyDbAccess.test_class)
            ctx.prepend_method_class()
            self.assertEqual(ctx.value, "DummyDbAccess:test_class")

        with self.subTest("STATICMETHOD"):
            ctx = tree.Context(dummy_api.DummyDbAccess.test_static)
            ctx.prepend_method_class()
            self.assertEqual(ctx.value, "DummyDbAccess:test_static")

        with self.subTest("FUNCTION"):
            ctx = tree.Context(dummy_api.dummy_func)
            ctx.prepend_method_class()
            self.assertEqual(ctx.value, "dummy_api:dummy_func")

        with self.subTest("DESCRIPTOR"):
            ctx = tree.Context(dummy_api.DummyDbAccess.__getattribute__)
            ctx.prepend_method_class()
            self.assertEqual(ctx.value, "object:__getattribute__")

        with self.subTest("DECORATOR"):
            ctx = tree.Context(dummy_api.test_decorator)
            ctx.prepend_method_class()
            self.assertEqual(ctx.value, "dummy_api:test_decorator")

        with self.subTest("PROPERTY"):
            pass  # TODO


class TestMethodTreeNode(unittest.TestCase):
    def test_init(self):
        node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        self.assertEqual(str(node.ctx), "test_method")
        self.assertEqual(node.children, [])
        self.assertIsNone(node.parent)

    def test_add_child(self):
        with self.subTest("ROOT ADD CHILD"):
            root = MethodTreeNode()
            node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
            root.add_child(node)
            self.assertEqual(root.children, [node])
            self.assertEqual(node.parent, weakref.ReferenceType(root))
            self.assertEqual(node.ctx.value, "DummyDbAccess:test_method")

        with self.subTest("CHILD ADD CHILD"):
            root = MethodTreeNode()
            node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
            root.add_child(node)
            node2 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
            node.add_child(node2)
            self.assertEqual(node.children, [node2])
            self.assertEqual(node2.parent, weakref.ReferenceType(node))
            self.assertEqual(node2.ctx.value, "DummyDbAccess:test_method.test_method")


class TestContextTree(unittest.TestCase):
    def test_init(self):
        ctx_tree = ContextTree()
        self.assertEqual(type(ctx_tree.root), MethodTreeNode)
        self.assertEqual(ctx_tree.root.ctx.value, "")

    def test_delete_node(self):
        ctx_tree = ContextTree()
        node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        ctx_tree.root.add_child(node)
        child1 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        node.add_child(child1)
        child2 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        node.add_child(child2)
        # -2 because 1 ref is in getrefcount call and one is above. We care about ref in root.parent
        self.assertEqual(sys.getrefcount(node) - 2, 1)
        # 1 child1.parent and child2.parent are same weakref
        self.assertEqual(len(weakref.getweakrefs(node)), 1)
        self.assertEqual(child1.parent, child2.parent)
        ctx_tree.delete_node(node)

        self.assertEqual(ctx_tree.root.children, [child1, child2])
        self.assertEqual(child1.parent, weakref.ReferenceType(ctx_tree.root))
        self.assertEqual(child2.parent, weakref.ReferenceType(ctx_tree.root))
        self.assertEqual(sys.getrefcount(node) - 1, 1)
        self.assertEqual(weakref.getweakrefcount(node), 0)

    @patch("src.phanos.tree.ContextTree.delete_node")
    def test_find_and_delete_node(self, mock_delete_node: MagicMock):
        ctx_tree = ContextTree()
        node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        ctx_tree.root.add_child(node)
        child1 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        node.add_child(child1)
        child2 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        node.add_child(child2)
        with self.subTest("FOUND"):
            self.assertTrue(ctx_tree.find_and_delete_node(node))
            mock_delete_node.assert_called_with(node)

        with self.subTest("NOT FOUND"):
            not_in_tree = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
            self.assertFalse(ctx_tree.find_and_delete_node(not_in_tree))

    @patch("src.phanos.tree.ContextTree.delete_node")
    def test_clear_tree(self, mock_delete_node: MagicMock):
        """Check method for tree clearing"""
        ctx_tree = ContextTree()
        node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        ctx_tree.root.add_child(node)
        child1 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        node.add_child(child1)
        child2 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        node.add_child(child2)

        ctx_tree.clear()
        self.assertEqual(mock_delete_node.call_count, 3)
        self.assertIsNotNone(ctx_tree.root)
