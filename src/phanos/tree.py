from __future__ import annotations

import inspect
import logging
import typing


class MethodTree:
    """
    Tree for storing method calls context
    """

    parent: typing.Optional[MethodTree]
    children: typing.List[MethodTree]
    method: typing.Optional[typing.Callable]
    context: str

    _logger: logging.Logger

    def __init__(
        self,
        method: typing.Optional[typing.Callable] = None,
        logger: typing.Optional[logging.Logger] = None,
    ) -> None:
        """Set method and nodes context

        :param method: method, which was decorated with @profile if None then root node
        """
        self.children = []
        self.parent = None
        self.method = None

        self.context = ""
        if method is not None:
            self.method = method
            self.context = method.__name__

        self._logger = logger or logging.getLogger(__name__)

    def add_child(self, child: MethodTree) -> MethodTree:
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
            child.context = self.context + "." + child.context
        self.children.append(child)
        self._logger.debug(f"Phanos - node {self.context} added child: {child.context}")
        return child

    def delete_child(self) -> None:
        """Delete first child of node"""
        child = self.children.pop(0)
        child.parent = None
        self._logger.debug(
            f"Phanos - node {self.context} deleted child: {child.context}"
        )

    def clear_tree(self) -> None:
        """Clears tree of all nodes from self"""
        for child in self.children:
            child.clear_tree()
        self.parent = None
        children = []
        for child in self.children:
            children.append(child.context)
        self.children.clear()
        self._logger.debug(f"Phanos - node {self.context} deleted children: {children}")

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
