from __future__ import annotations

import inspect
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

    top_module: str

    def __init__(
        self,
        method: typing.Optional[typing.Callable] = None,
        logger: typing.Optional[log.LoggerLike] = None,
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

            module = inspect.getmodule(self.method)
            # if module is None -> builtin, but that shouldn't happen
            self.top_module = __import__(module.__name__.split(".")[0]).__name__ if module else ""

    def add_child(self, child: MethodTreeNode) -> MethodTreeNode:
        """Add child to method tree node

        Adds child to tree node. Sets Context string of child node

        :param child: child to be inserted
        """
        child.parent = self
        if self.method is None:  # equivalent of 'self.context != ""' -> i am root
            child.context = self.get_method_class(child.method) + ":" + child.context  # child.method cannot be None
        else:
            between = self.get_methods_between()
            if between != "":
                child.context = self.context + "." + between + "." + child.context
            else:
                child.context = self.context + "." + child.context
        self.children.append(child)
        self.debug(f"{self.add_child.__qualname__}: node {self.context!r} added child: {child.context!r}")
        return child

    def delete_child(self) -> None:
        """Delete first child of node"""
        try:
            child = self.children.pop(0)
            child.parent = None
            self.debug(f"{self.delete_child.__qualname__}: node {self.context!r} deleted child: {child.context!r}")
        except IndexError:
            self.debug(f"{self.delete_child.__qualname__}: node {self.context!r} do not have any children")

    def clear_tree(self) -> None:
        """Deletes whole subtree starting from this node"""
        for child in self.children:
            child.clear_tree()
        self.clear_children()

    def clear_children(self):
        """Clears children and unset parent of this node"""
        self.parent = None
        children = []
        for child in self.children:
            children.append(child.context)
        self.children.clear()
        self.debug(f"{self.clear_children.__qualname__}: node {self.context!r} deleted children: {children}")

    @staticmethod
    def get_method_class(meth: typing.Callable) -> str:
        """
        Gets owner(class or module) name where specified method/function was defined.

        Cannot do: partial, lambda !!!!!

        Can do: rest

        :param meth: method/function to inspect
        :return: owner name where method was defined, owner could be class or module
        """
        if inspect.ismethod(meth):
            # noinspection PyUnresolvedReferences
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
        # noinspection SpellCheckingInspection
        class_ = getattr(meth, "__objclass__", None)
        # handle special descriptor objects
        if class_ is not None:
            return class_.__name__
        module = inspect.getmodule(meth)

        return module.__name__.split(".")[-1] if module else ""

    def get_methods_between(self) -> str:
        """Creates string from methods between `parent.method` and `self.method`

        :returns: Method calling context string. Example: "method1.method2.method3"
        """
        methods_between = []
        split_context = self.context.split(".")
        if len(split_context) == 1:
            starting_method = self.context.split(":")[-1]
        else:
            starting_method = split_context[-1]
        between = ""
        if inspect.stack():
            for frame in inspect.stack():
                if frame.function == starting_method:
                    break
                method_module = inspect.getmodule(frame[0])
                method_module = method_module.__name__.split(".")[0] if method_module else ""
                # first condition checks if method have same top module as self.method
                # second condition ignores <lambda>, <genexp>, <listcomp>...
                if method_module == self.top_module and frame.function[0] != "<":
                    methods_between.append(frame.function)
            methods_between.reverse()
            between = ".".join(f"{method}" for method in methods_between)

        return between
