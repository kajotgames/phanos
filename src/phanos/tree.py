""" Module containing Classes for context tree management """
from __future__ import annotations

import inspect
import logging
import typing
import weakref


from . import log
from .types import LoggerLike


class Context:
    """Class for keeping and managing context of one MethodTreeNode

    Context is string representing call order of methods decorated with @profile.

    Example: If method `ClassX.root_method` calls `ClassY.method_y` which calls `ClassZ.method_z`
    and all of mentioned methods are decorated with @profile, `Context.value` for method `ClassZ.method_z` will be:
    'ClassX:root_method.method_y.method_z'. If any of mentioned methods isn't decorated with @profile, its name
    will not be added to `Context.value`.
    """

    # method for which to keep context
    method: typing.Optional[typing.Callable]
    value: str

    def __init__(self, method: typing.Optional[typing.Callable] = None) -> None:
        """Stores method and set initial context value

        :param method: Any Callable, must be passed. self.method=None is reserved for root node
        """
        self.method = method
        if method:
            self.value = method.__name__
            return
        self.value = ""

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return "'" + self.value + "'"

    def prepend_method_class(self) -> None:
        """
        Gets owner(class or module) name where `self.method` was defined and prepend it to current `self.value`.

        CANNOT DO: partial, lambda, property

        Can do:  method, classmethod, staticmethod, function ,decorator, descriptor
        """
        meth = self.method
        if inspect.ismethod(meth):
            # noinspection PyUnresolvedReferences
            for cls in inspect.getmro(meth.__self__.__class__):
                if meth.__name__ in cls.__dict__:
                    self.value = cls.__name__ + ":" + self.value
                    return

            meth = getattr(meth, "__func__", meth)
        if inspect.isfunction(meth):
            cls_ = getattr(
                inspect.getmodule(meth),
                meth.__qualname__.split(".<locals>", 1)[0].rsplit(".", 1)[0],
                None,
            )
            if isinstance(cls_, type):
                self.value = cls_.__name__ + ":" + self.value
                return
        # noinspection SpellCheckingInspection
        class_ = getattr(meth, "__objclass__", None)
        # handle special descriptor objects
        if class_ is not None:
            self.value = class_.__name__ + ":" + self.value
            return

        module = inspect.getmodule(meth)
        self.value = (module.__name__.split(".")[-1] if module else "") + ":" + self.value


class ContextTree(log.InstanceLoggerMixin):
    """ContextTree is tree structure which stores graph of calling order of methods decorated with @profile"""

    root: MethodTreeNode

    def __init__(self, logger: typing.Optional[LoggerLike] = None) -> None:
        """Configure logger and initialize root node"""
        super().__init__(logged_name="phanos", logger=logger or logging.getLogger(__name__))
        self.root = MethodTreeNode(logger=self.logger)

    def delete_node(self, node: MethodTreeNode) -> bool:
        """Clears all references for specified node in tree and delete it,
        modify tree, so that all children of deleted node are moved to parent of deleted node

        :param node: node which should be deleted
        """
        if node is self.root:
            self.warning(f"{self.find_and_delete_node.__qualname__}: cannot delete root node")
            return False

        if node.parent is not None:
            node.parent.children.remove(node)
            node.parent.children.extend(node.children)
        for child_to_move in node.children:
            child_to_move.parent = node.parent
        node.children.clear()
        node.parent = None
        self.debug(f"{self.delete_node.__qualname__}: node {node.ctx!r} deleted")
        del node
        return True

    def _find_and_delete_node(self, node: MethodTreeNode, root: MethodTreeNode) -> bool:
        """Searches for node in subtree starting from `root` and deletes it

        :param node: node to be deleted
        :param root: root of subtree
        """
        if root is node:
            deleted = self.delete_node(node)
            return deleted

        for child in root.children:
            return self._find_and_delete_node(node, child)

        return False

    def find_and_delete_node(self, node: MethodTreeNode, root: typing.Optional[MethodTreeNode] = None) -> bool:
        """Deletes one node from ContextTree. if param `root` is passed, tree will be searched from this node
        else search begin from `self.root`. Cannot delete 'self.root' node

        :param node: node which to delete, cannot be 'self.root'
        :param root: root of ContextTree.
        :returns: True if node was found and deleted, False otherwise
        """
        if root is None:
            root = self.root

        return self._find_and_delete_node(node, root)

    def _clear(self, root: MethodTreeNode) -> None:
        """Deletes whole subtree starting from param 'root'. Deletes from bottom to top"""
        for child in root.children:
            self._clear(child)

        if not root == self.root:
            self.delete_node(root)

    def clear(self, root: typing.Optional[MethodTreeNode] = None) -> None:
        """Deletes whole subtree starting from param 'root'. If param root is not passed, 'self.root' is used

        If 'root' == 'self.root', then 'self.root' is kept. otherwise 'root' is deleted

        :param root: Node from which to start deleting tree.
        """
        if root is None:
            root = self.root

        self._clear(root)


class MethodTreeNode(log.InstanceLoggerMixin):
    """
    Class representing one node of ContextTree
    """

    _parent: typing.Optional[weakref.ReferenceType]
    children: typing.List[MethodTreeNode]
    ctx: Context

    def __init__(
        self,
        method: typing.Optional[typing.Callable] = None,
        logger: typing.Optional[LoggerLike] = None,
    ) -> None:
        """Configures logger, initialize `Context`

        :param method: method, which was decorated with @profile. If node isn't root, then must be passed
        :param logger: logger instance
        """
        super().__init__(logged_name="phanos", logger=logger)
        self.children = []
        self.parent = None
        self.ctx = Context(method)

    @property
    def parent(self) -> typing.Optional[MethodTreeNode]:
        """Getter for parent node"""
        return self._parent() if self._parent else None

    @parent.setter
    def parent(self, parent: typing.Optional[MethodTreeNode]) -> None:
        """Setter for parent node"""
        self._parent = weakref.ref(parent) if parent else None

    def add_child(self, child: MethodTreeNode) -> MethodTreeNode:
        """Add child node to `self`

        Adds child to tree node. Sets Context string of child node as `self.ctx.value` + `child.ctx.value`.
        If `self` is root, then sets child Context as '`child.method.(class or module name)`:`child.method.__name__`'

        :param child: child to be inserted
        :returns: child parameter
        """
        child.parent = self
        if self.ctx.method is None:  # is root
            child.ctx.prepend_method_class()
        else:
            child.ctx.value = self.ctx.value + "." + child.ctx.value
        self.children.append(child)
        self.debug(f"{self.add_child.__qualname__}: node {self.ctx!r} added child: {child.ctx!r}")
        return child
