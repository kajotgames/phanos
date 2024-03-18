import sys
import unittest
import weakref
from unittest.mock import patch, MagicMock

from phanos import tree
from src.phanos.tree import MethodTreeNode, ContextTree
from test import dummy_api

SKIP_REASON_INIT = "Fails for sure if `test_init` fails, but not for reasons tested here"


def construct_tree():
    """Construct tree for testing purposes
    structure:
    root
    ├── node
    │   ├── child1
    │   └── child2


    :returns: tuple of tree, root, child1, child2
    """
    ctx_tree = ContextTree()
    node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
    ctx_tree.root.add_child(node)
    child1 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
    node.add_child(child1)
    child2 = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
    node.add_child(child2)
    return ctx_tree, node, child1, child2


class TestContext(unittest.TestCase):
    BASIC_METHODS = [dummy_api.DummyDbAccess.test_method, None]
    ADVANCED_METHODS = {
        dummy_api.DummyDbAccess.test_method: "DummyDbAccess:test_method",
        dummy_api.DummyDbAccess.test_class: "DummyDbAccess:test_class",
        dummy_api.DummyDbAccess.test_static: "DummyDbAccess:test_static",
        dummy_api.dummy_func: "dummy_api:dummy_func",
        dummy_api.DummyDbAccess.__getattribute__: "object:__getattribute__",
        dummy_api.test_decorator: "dummy_api:test_decorator",
    }

    def test_init(self):
        for method in TestContext.BASIC_METHODS:
            with self.subTest(method=method):
                ctx = tree.Context(method)
                self.assertEqual(ctx.method, method)
                self.assertEqual(ctx.value, method.__name__ if method else "")

    @unittest.skipUnless(test_init, SKIP_REASON_INIT)
    def test_str_and_repr(self):
        for method in TestContext.BASIC_METHODS:
            with self.subTest(method=method):
                ctx = tree.Context(method)
                self.assertEqual(str(ctx), ctx.value)
                self.assertEqual(repr(ctx), "'" + ctx.value + "'")

    @unittest.skipUnless(test_init, SKIP_REASON_INIT)
    def test_prepend_method_class(self):
        """Check if method prepends class or module name to value correctly"""
        for method, expected in TestContext.ADVANCED_METHODS.items():
            with self.subTest(method=method):
                ctx = tree.Context(method)
                ctx.prepend_method_class()
                self.assertEqual(ctx.value, expected)


class TestMethodTreeNode(unittest.TestCase):
    @patch("src.phanos.tree.Context")
    def test_init(self, mock_context: MagicMock):
        node = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
        self.assertEqual(node.children, [])
        self.assertIsNone(node.parent)
        mock_context.assert_called_once_with(dummy_api.DummyDbAccess.test_method)

    @unittest.skipUnless(test_init, SKIP_REASON_INIT)
    @patch("src.phanos.tree.Context")
    def test_add_child_to_root(self, mock_context: MagicMock):
        parent = MethodTreeNode()
        child = MethodTreeNode(dummy_api.DummyDbAccess.test_method)

        mock_context.return_value.method = None
        mock_context.return_value.value = ""
        with self.subTest("no context"):
            parent.add_child(child)
            self.assertEqual(parent.children, [child])
            self.assertEqual(child.parent, parent)
            mock_context.return_value.prepend_method_class.assert_called_once()

        mock_context.reset_mock()
        mock_context.return_value.method = dummy_api.DummyDbAccess.test_method
        tmp_value = mock_context.return_value.value = "n"
        with self.subTest("context_exists"):
            parent.add_child(child)
            self.assertEqual(parent.children, [child, child])
            self.assertEqual(child.parent, parent)
            mock_context.return_value.prepend_method_class.assert_not_called()
            self.assertEqual(child.ctx.value, tmp_value + "." + tmp_value)

    def test_parent_property(self):
        parent_node = MethodTreeNode()
        parents = [None, MethodTreeNode()]
        for parent in parents:
            with self.subTest(parent=parent):
                parent_node.parent = parent
                self.assertEqual(parent_node.parent, parent)


class TestContextTree(unittest.TestCase):
    def test_init(self):
        ctx_tree = ContextTree()
        self.assertEqual(type(ctx_tree.root), MethodTreeNode)
        self.assertEqual(ctx_tree.root.ctx.value, "")

    @unittest.skipUnless(test_init, SKIP_REASON_INIT)
    def test_delete_node(self):
        ctx_tree, node, child1, child2 = construct_tree()
        with self.subTest("leaf node"):
            ctx_tree.delete_node(child1)
            self.assertEqual(node.children, [child2])
            self.assertIsNone(child1.parent)

            self.assertEqual(child1.children, [])
            self.assertEqual(weakref.getweakrefcount(node), 0)  # check if weakref is deleted

        ctx_tree, node, child1, child2 = construct_tree()
        with self.subTest("middle node"):
            ctx_tree.delete_node(node)
            self.assertEqual(ctx_tree.root.children, [child1, child2])
            self.assertEqual(child1.parent, ctx_tree.root)
            self.assertEqual(child2.parent, ctx_tree.root)

            self.assertIsNone(node.parent)
            self.assertEqual(node.children, [])
            self.assertEqual(weakref.getweakrefcount(node), 0)  # check if weakref is deleted

        ctx_tree, node, child1, child2 = construct_tree()
        with self.subTest("root node"):
            self.assertFalse(ctx_tree.delete_node(ctx_tree.root))
            self.assertEqual(node.parent, ctx_tree.root)

    @unittest.skipUnless(test_init, SKIP_REASON_INIT)
    @patch("src.phanos.tree.ContextTree.delete_node")
    def test_find_and_delete_node(self, mock_delete_node: MagicMock):
        ctx_tree, node, child1, child2 = construct_tree()

        with self.subTest("not found"):
            not_in_tree = MethodTreeNode(dummy_api.DummyDbAccess.test_method)
            self.assertFalse(ctx_tree.find_and_delete_node(not_in_tree))
            mock_delete_node.assert_not_called()

        with self.subTest("found"):
            self.assertTrue(ctx_tree.find_and_delete_node(node))
            mock_delete_node.assert_called_with(node)

    @unittest.skipUnless(test_init, SKIP_REASON_INIT)
    @patch("src.phanos.tree.ContextTree.delete_node")
    def test_clear(self, mock_delete_node: MagicMock):
        """Check method for tree clearing"""
        ctx_tree, node, child1, child2 = construct_tree()

        ctx_tree.clear()

        self.assertEqual(mock_delete_node.call_count, 3)
        call_nodes = [call[0][0] for call in mock_delete_node.call_args_list]
        self.assertIn(node, call_nodes)
        self.assertIn(child1, call_nodes)
        self.assertIn(child2, call_nodes)
