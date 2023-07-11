from __future__ import annotations

import inspect
import logging
import typing
from . import log


class MethodTreeNode(log.InstanceLoggerMixin):
    """
    Tree for storing method calls context
    """

    parent: typing.Optional[MethodTreeNode]
    children: typing.List[MethodTreeNode]
    method: typing.Optional[typing.Callable]
    context: str

    def __init__(
        self,
        method: typing.Optional[typing.Callable] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """Set method and nodes context

        :param method: method, which was decorated with @profile if None then root node
        """
        super().__init__(logged_name="phanos", logger=logger)
        self.children = []
        self.parent = None
        self.method = None

        self.context = ""
        if method is not None:
            self.method = method
            self.context = method.__name__

    def add_child(self, child: MethodTreeNode) -> MethodTreeNode:
        """Add child to method tree node

        Adds child to tree node. Sets Context string of child node

        :param child: child to be inserted
        """
        child.parent = self
        if self.method is None:  # equivalent of 'self.context != ""' -> i am root
            child.context = (
                self.get_method_class(child.method) + ":" + child.context
            )  # child.method cannot be None
        else:
            between = self._get_methods_between()
            if between != "":
                child.context = self.context + "." + between + "." + child.context
            else:
                child.context = self.context + "." + child.context
        self.children.append(child)
        self.debug(f"node {self.context} added child: {child.context}")
        return child

    def _get_methods_between(self) -> str:
        methods_between = []
        split_context = self.context.split(".")
        if len(split_context) == 1:
            starting_method = self.context.split(":")[-1]
        else:
            starting_method = split_context[-1]
        between = ""
        if inspect.stack():
            for item in inspect.stack():
                if item.function == starting_method:
                    break
                if item.function not in [
                    "<module>",
                    "inner",
                    "add_child",
                    "_get_methods_between",
                ]:
                    methods_between.append(item.function)
            methods_between.reverse()
            between = ".".join(f"{method}" for method in methods_between)

        return between

    def delete_child(self) -> None:
        """Delete first child of node"""
        child = self.children.pop(0)
        child.parent = None
        self.debug(f"node {self.context} deleted child: {child.context}")

    def clear_tree(self) -> None:
        """Clears tree of all nodes from self"""
        for child in self.children:
            child.clear_tree()
        self._clear_children()

    def _clear_children(self):
        self.parent = None
        children = []
        for child in self.children:
            children.append(child.context)
        self.children.clear()
        self.debug(f"node {self.context} deleted children: {children}")

    @staticmethod
    def get_method_class(meth: typing.Callable) -> str:
        """
        Gets class/module name where specified method/function was defined.

        Cannot do: partial, lambda !!!!!

        Can do: rest

        :param meth: method where to discover class
        :return: class name where method was defined if was defined in class else module name
        """
        if inspect.ismethod(meth):
            for cls in inspect.getmro(meth.__self__.__class__):
                if meth.__name__ in cls.__dict__:
                    return cls.__name__
            meth = getattr(meth, "__func__", meth)
        if inspect.isfunction(meth):
            cls_ = getattr(
                inspect.getmodule(meth),
                meth.__qualname__.split(".<locals>", 1)[0].rsplit(".", 1)[0],
                None,
            )
            if isinstance(cls_, type):
                return cls_.__name__
        class_ = getattr(
            meth, "__objclass__", None
        )  # handle special descriptor objects
        if class_ is not None:
            return class_.__name__
        module = inspect.getmodule(meth)

        return module.__name__.split(".")[-1] if module else ""
