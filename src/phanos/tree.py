""" Module containing Classes for context tree management """
from __future__ import annotations

# contextvars package is builtin but PyCharm do not recognize it
# noinspection PyPackageRequirements
import contextvars
import inspect
import logging
import typing
import weakref


from . import log
from .types import LoggerLike

# context var storing currently processed node. Is not part of MethodTree because of async
curr_node: contextvars.ContextVar = contextvars.ContextVar("curr_node")


class Context:
    """Class for keeping and managing context of one MethodTreeNode

    Context is string representing call order of methods decorated with @profile.

    Example: If method `ClassX.root_method` calls `ClassY.method_y` which calls `ClassZ.method_z`
    and all of mentioned methods are decorated with @profile, `Context.value` for method `ClassZ.method_z` will be:
    'ClassX:root_method.method_y.method_z'. If any of mentioned methods isn't decorated with @profile, its name
    will not be added to `Context.value`.
    """

    # top module of root_method
    top_module: typing.Optional[str]
    # method for which to keep context
    method: typing.Optional[typing.Callable]

    value: str

    def __init__(self, method: typing.Optional[typing.Callable] = None) -> None:
        """Stores method amd set initial context value and top_module
        :param method: method of MethodTreeNode object
        """
        self.method = method
        if method:
            module = inspect.getmodule(self.method)
            self.value = method.__name__
            self.top_module = __import__(module.__name__.split(".")[0]).__name__ if module else ""
            return
        self.top_module = None
        self.value = ""

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value

    def prepend_method_class(self) -> None:
        """
        Gets owner(class or module) name where `self.method` was defined and prepend it to current `self.value`.

        CANNOT DO: partial, lambda

        Can do: rest
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

    def delete_node(self, node: MethodTreeNode) -> None:
        """Clears all references for specified node and delete it

        :param node: node which should be deleted
        """
        node_parent: typing.Optional[MethodTreeNode] = None
        if node.parent:
            node_parent = node.parent()
        try:
            if isinstance(node_parent, MethodTreeNode):
                node_parent.children.remove(node)
                node_parent.children.extend(node.children)
            for child_to_move in node.children:
                child_to_move.parent = node.parent
            node.children = []
            node.parent = None
            self.debug(f"{self.delete_node.__qualname__}: node {node.ctx!r} deleted")
            del node
        except ValueError:
            pass

    def find_and_delete_node(self, node: MethodTreeNode, root: typing.Optional[MethodTreeNode] = None) -> bool:
        """Deletes one node from ContextTree. if param `root` is passed, tree will be searched from this node
        else search begin from `self.root`.

        :param node: node which to delete
        :param root: root of ContextTree.
        """
        if root is None:
            root = self.root

        if root is node:
            self.delete_node(node)
            return True

        for child in root.children:
            return self.find_and_delete_node(node, child)

        return False

    def clear(self, root: typing.Optional[MethodTreeNode] = None) -> None:
        """Deletes whole subtree starting from param root. If param root is not passed, `self.root` is used

        :param root: Node from which to start deleting tree.
        """
        if root is None:
            root = self.root
        for child in root.children:
            self.clear(child)
        self.delete_node(root)
        self.debug(f"{self.clear.__qualname__}: tree cleared")


class MethodTreeNode(log.InstanceLoggerMixin):
    """
    Class representing one node of ContextTree
    """

    parent: typing.Optional[weakref.ReferenceType]
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

    def add_child(self, child: MethodTreeNode) -> MethodTreeNode:
        """Add child node to `self`

        Adds child to tree node. Sets Context string of child node as `self.ctx.value` + `child.ctx.value`.
        If `self` is root, then sets child Context as '`child.method.(class or module name)`:`child.method.__name__`'

        :param child: child to be inserted
        :returns: child parameter
        """
        child.parent = weakref.ref(self)
        if self.ctx.method is None:  # equivalent of 'self.context != ""' -> i am root
            child.ctx.prepend_method_class()
        else:
            child.ctx.value = self.ctx.value + "." + child.ctx.value
        self.children.append(child)
        self.debug(f"{self.add_child.__qualname__}: node {self.ctx!r} added child: {child.ctx!r}")
        return child

    def delete_child(self) -> None:
        """Delete first child of `self`.

        :raises IndexError: If `self.children` is empty
        """
        try:
            child = self.children.pop(0)
            child.parent = None
            del child
            self.debug(f"{self.delete_child.__qualname__}: node {self.ctx!r} deleted child: {self.ctx!r}")
        except IndexError:
            self.debug(f"{self.delete_child.__qualname__}: node {self.ctx!r} do not have any children")
