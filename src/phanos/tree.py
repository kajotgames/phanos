from __future__ import annotations

import functools
import inspect
import typing


class MethodTree:
    """
    Tree for storing method calls context
    """

    parent: typing.Optional[MethodTree]
    children: typing.List[MethodTree]
    method: typing.Optional[callable]
    class_: typing.Optional[str]
    context: str

    def __init__(self, method: typing.Optional[callable] = None) -> None:
        """Set method and nodes context

        :param method: method, which was decorated with @profile if None then root node
        """
        self.children = []
        self.parent = None

        self.context = ""
        if method is not None:
            self.method = method
            self.context = method.__name__

    def add_child(self, child: MethodTree) -> MethodTree:
        """Add child to method tree node

        Adds child to tree node. Sets Context string of child node

        :param child: child to be inserted
        """
        child.parent = self
        if self.context != "":
            child.context = self.context + "." + child.context
        else:
            child.context = self.get_method_class(child.method) + ":" + child.context
        self.children.append(child)
        return child

    def delete_child(self) -> None:
        """Delete first child of node"""
        child = self.children.pop(0)
        child.parent = None

    @staticmethod
    def get_method_class(meth: callable) -> str:
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
            meth = getattr(meth, "__func__", meth)  # fallback to __qualname__ parsing
        if inspect.isfunction(meth):
            cls = getattr(
                inspect.getmodule(meth),
                meth.__qualname__.split(".<locals>", 1)[0].rsplit(".", 1)[0],
                None,
            )
            if isinstance(cls, type):
                return cls.__name__
        class_ = getattr(
            meth, "__objclass__", None
        )  # handle special descriptor objects
        if class_ is not None:
            return class_.__name__
        module = inspect.getmodule(meth).__name__

        return module.split(".")[-1]
