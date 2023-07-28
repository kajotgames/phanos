from __future__ import annotations

import inspect
import logging
import typing
from datetime import datetime

from . import log


class Context:
    """class for keeping and managing MethodTreeNode context

    :attr asdf: asdf
    """

    top_module: typing.Optional[str]
    context: str
    method: typing.Optional[typing.Callable]
    creation_ts: datetime

    def __init__(self, method: typing.Optional[typing.Callable] = None):
        """

        :param method: method of MethodTreeNode object
        """
        self.creation_ts = datetime.now()
        self.method = method
        if method:
            module = inspect.getmodule(self.method)
            self.context = method.__name__
            # if module is None -> builtin, but that shouldn't happen

            self.top_module = __import__(module.__name__.split(".")[0]).__name__ if module else ""
            return
        self.top_module = None
        self.context = ""

    def __str__(self):
        return self.context

    def __repr__(self):
        return self.context

    def prepend_method_class(self) -> None:
        """
        Gets owner(class or module) name where specified method/function was defined.

        Cannot do: partial, lambda !!!!!

        Can do: rest

        :return: owner name where method was defined, owner could be class or module
        """
        meth = self.method
        if inspect.ismethod(meth):
            # noinspection PyUnresolvedReferences
            for cls in inspect.getmro(meth.__self__.__class__):
                if meth.__name__ in cls.__dict__:
                    self.context = cls.__name__ + ":" + self.context
                    return

            meth = getattr(meth, "__func__", meth)
        if inspect.isfunction(meth):
            cls_ = getattr(
                inspect.getmodule(meth),
                meth.__qualname__.split(".<locals>", 1)[0].rsplit(".", 1)[0],
                None,
            )
            if isinstance(cls_, type):
                self.context = cls_.__name__ + ":" + self.context
                return
        # noinspection SpellCheckingInspection
        class_ = getattr(meth, "__objclass__", None)
        # handle special descriptor objects
        if class_ is not None:
            self.context = class_.__name__ + ":" + self.context
            return

        module = inspect.getmodule(meth)
        self.context = (module.__name__.split(".")[-1] if module else "") + ":" + self.context

    def compose_child_context(self, child: Context) -> None:
        """Creates string from methods between `parent.method` and `self.method`

        :returns: Method calling context string. Example: "method1.method2.method3"
        """
        methods_between = []
        starting_method = self.method.__name__.split(":")[-1]
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

        if between != "":
            child.context = self.context + "." + between + "." + child.context
        else:
            child.context = self.context + "." + child.context

    def find_context(self, root) -> None:
        context = []
        root_methods_names = [str(child.ctx).split(":")[1] for child in root.children]
        root_methods_classes = [str(child.ctx).split(":")[0] for child in root.children]
        cls_ = None
        for frm in inspect.stack():
            method_module = inspect.getmodule(frm[0])
            method_module = method_module.__name__.split(".")[0] if method_module else ""
            # first condition checks if method have same top module as self.method
            # second condition ignores <lambda>, <genexp>, <listcomp>, ...
            if method_module == self.top_module and frm.function[0] != "<":
                context.append(frm.function)
            # get class from `frm`
            if frm.function in root_methods_names:
                cls_ = self.get_class_from_frame(frm.frame)
                if cls_ in root_methods_classes:
                    break
        if cls_:
            context.reverse()
            between = ".".join(f"{method}" for method in context)
            self.context = cls_ + ":" + between + "." + self.method.__name__
        else:
            self.prepend_method_class()

    @staticmethod
    def get_class_from_frame(fr) -> typing.Optional[str]:
        args, _, _, value_dict = inspect.getargvalues(fr)
        if len(args):
            # normal method
            if args[0] == "self":
                instance = value_dict.get("self", None)
                if instance:
                    return getattr(instance, "__class__", None).__name__
            # class method
            if args[0] == "cls":
                instance = value_dict.get("cls", None)
                if instance:
                    return instance.__name__

        # static method
        module = inspect.getmodule(fr)
        codename = fr.f_code.co_name
        classes = [getattr(module, name) for name in dir(module) if inspect.isclass(getattr(module, name))]
        for cls in classes:
            if hasattr(cls, codename):
                fobj = getattr(cls, codename)
                code = fobj.__closure__[0].cell_contents.__code__
                if code == fr.f_code:
                    return fobj.__closure__[0].cell_contents.__qualname__.split(".")[0]

        # function module
        return module.__name__.split(".")[-1] if module else None


class ContextTree(log.InstanceLoggerMixin):
    root: MethodTreeNode
    current_node: MethodTreeNode

    def __init__(self, logger=None):
        super().__init__(logged_name="phanos", logger=logger or logging.getLogger(__name__))
        self.root = MethodTreeNode(logger=self.logger)
        self.current_node = self.root

    def insert(self, node: MethodTreeNode, root: typing.Optional[MethodTreeNode] = None) -> None:
        if root is None:
            root = self.root
        node_context = str(node.ctx).split(":")[1].split(".")
        for child in root.children:
            # find match between `child.context` and `node.context`
            child_context = str(child.ctx).split(":")[1].split(".")
            max_search = min(len(child_context), len(node_context))
            for pos in reversed(range(max_search)):
                if child_context[pos] == node_context[pos]:
                    _ = child_context.pop(pos)
                    _ = node_context.pop(pos)
            # complete child.context match -> look for better match deeper in tree -> recursion
            if not len(child_context) and len(node_context):
                self.insert(node, child)
                return
            # complete `node.context` match -> no better match can be found
            # -> insert in current depth, `node` will be `child`s parent
            if len(child_context) and not len(node_context):
                parent_context = str(root.parent.ctx) if root.parent and root.parent.ctx.context != "" else "root"
                self.debug(f"middle tree insert - node: {node.ctx!r} to parent: {parent_context!r}")
                node.children = child.parent.children.copy()
                child.parent.children.clear()
                child.parent.children.append(node)
                node.parent = child.parent
                for child_ in node.children:
                    child_.parent = node
                return
            # identical context ->
            if not len(child_context) and not len(node_context):
                pass
        # no complete match -> insert as leaf, `node.parent` will be previous best match (root)
        parent_context = str(root.ctx) if root.ctx.context != "" else "root"
        self.debug(f"appending leaf node: {node.ctx!r} to parent: {parent_context!r}")
        root.children.append(node)
        node.parent = root
        return

    def find_context_and_insert(self, node: MethodTreeNode) -> None:
        node.ctx.find_context(self.root)
        self.insert(node)

    def delete_node(self, node: MethodTreeNode, root: typing.Optional[MethodTreeNode] = None) -> None:
        # TODO: find timestamp, how to save it
        if root is None:
            root = self.root
        for child in root.children:
            if child is node:
                node.parent.children.remove(node)
                node.parent.children.extend(node.children)

                for child_to_move in node.children:
                    child_to_move.parent = node.parent
                break
            self.delete_node(node, child)

    def clear(self, root: typing.Optional[MethodTreeNode] = None) -> None:
        """Deletes whole subtree starting from this node"""
        if root is None:
            root = self.root
        for child in root.children:
            self.clear(child)
        root.clear_children()

    def postorder_print(self, node: typing.Optional[MethodTreeNode] = None):
        print("sup")
        if node is None:
            node = self.root
        for child in node.children:
            self.postorder_print(child)
        children_context = []
        for child in node.children:
            children_context.append(str(child.ctx))
        parent_context = str(node.parent.ctx) if node.parent and node.parent.ctx.context != "" else "root"
        self_context = str(node.ctx) if str(node.ctx) != "" else "root"
        self.debug(f"{self_context} with parent {parent_context!r} " f" and children {children_context!r}")

    def is_at_root(self):
        return self.current_node is self.root


class MethodTreeNode(log.InstanceLoggerMixin):
    """
    Tree for storing method calls context
    """

    parent: typing.Optional[MethodTreeNode]
    children: typing.List[MethodTreeNode]

    ctx: Context

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
        self.ctx = Context(method)

    def add_child(self, child: MethodTreeNode) -> MethodTreeNode:
        """Add child to method tree node

        Adds child to tree node. Sets Context string of child node

        :param child: child to be inserted
        """
        child.parent = self
        if self.ctx.method is None:  # equivalent of 'self.context != ""' -> i am root
            child.ctx.prepend_method_class()
        else:
            self.ctx.compose_child_context(child.ctx)
        self.children.append(child)
        self.debug(f"{self.add_child.__qualname__}: node {self.ctx!r} added child: {self.ctx!r}")
        return child

    def delete_child(self) -> None:
        """Delete first child of node"""
        try:
            child = self.children.pop(0)
            child.parent = None
            self.debug(f"{self.delete_child.__qualname__}: node {self.ctx!r} deleted child: {self.ctx!r}")
        except IndexError:
            self.debug(f"{self.delete_child.__qualname__}: node {self.ctx!r} do not have any children")

    def clear_children(self):
        """Clears children and unset parent of this node"""
        self.parent = None
        children = []
        for child in self.children:
            children.append(str(child.ctx))
        self.children.clear()
        self.debug(f"{self.clear_children.__qualname__}: node {self.ctx!r} deleted children: {children}")
