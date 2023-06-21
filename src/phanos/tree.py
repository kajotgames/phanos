from __future__ import annotations

import functools
import inspect
import typing


class MethodTree:
    """Class for storing order of method calls with its names"""

    parent: typing.Optional[MethodTree]
    children: typing.List[MethodTree]
    method: typing.Optional[typing.Callable]
    class_: typing.Optional[str]
    context: str

    def __init__(self, method: typing.Optional[str, typing.Callable] = None) -> None:
        self.children = []
        self.parent = None

        self.context = ""
        if method is not None:
            self.method = method
            self.context = method.__name__

    def add_child(self, child: MethodTree) -> MethodTree:
        """Add child to method tree node
        :param child: child to be inserted
        """
        child.parent = self
        if self.context != "":
            child.context = self.context + "." + child.context
        else:
            child.context = (
                self.get_method_class(child.method).__name__ + ":" + child.context
            )
        print(child.context)
        self.children.append(child)
        return child

    def delete_child(self) -> None:
        """Delete first child of node"""
        _ = self.children.pop(0)

    def get_method_class(self, meth):
        """
        neresi: partial, lambda
        resi: static, mimo classu, abstract,
        kdyz: class method -> tak prve classmethod pak profiling

        :param meth:
        :return:
        """
        if inspect.ismethod(meth):
            for cls in inspect.getmro(meth.__self__.__class__):
                if meth.__name__ in cls.__dict__:
                    return cls
            meth = getattr(meth, "__func__", meth)  # fallback to __qualname__ parsing
        if inspect.isfunction(meth):
            cls = getattr(
                inspect.getmodule(meth),
                meth.__qualname__.split(".<locals>", 1)[0].rsplit(".", 1)[0],
                None,
            )
            if isinstance(cls, type):
                return cls
        class_ = getattr(
            meth, "__objclass__", None
        )  # handle special descriptor objects
        if class_ is not None:
            return class_
        return inspect.getmodule(meth)
