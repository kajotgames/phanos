from __future__ import annotations

import inspect
import typing
from . import log


class ContextTree:
    root: MethodTreeNode
    current_node: MethodTreeNode

    longest_context: int
    root_method: typing.Optional[typing.Callable]
    # top Module???

    def __init__(self):
        self.root = MethodTreeNode()
        self.current_node = self.root
        self.longest_context = 0
        self.root_method = None

    def insert_into_tree(self, node: MethodTreeNode) -> None:
        split_context = node.context.split(":")[1].split(".")
        self._insert_into_tree(node, self.root, split_context)
        self.longest_context = max(self.longest_context, len(split_context))

        # TODO: debug log
        # self.debug(f"{self.insert_into_tree.__qualname__}: node {self.context!r} added child: {child.context!r}")

    def postorder(self, node: typing.Optional[MethodTreeNode] = None):
        if node is None:
            node = self.root
        for child in node.children:
            self.postorder(child)
        children_context = []
        for child in node.children:
            children_context.append(child.context)
        parent_context = node.parent.context if node.parent and node.parent.context != "" else "root"
        self_context = node.context if node.context != "" else "root"
        print(f"{self_context} with parent {parent_context} " f" and children {children_context}")

    def _find_context(self):
        pass

    def find_context_and_insert(self, node: MethodTreeNode):
        print(node.method.__name__)
        if self.longest_context == 0:
            node.context = node.get_method_class(node.method) + ":" + node.context
            self.longest_context = 1
            self.root_method = node.method
        else:
            print("find_context in stack")
            context = []
            found = False
            for frm in inspect.stack():
                print(frm.function)
                method_module = inspect.getmodule(frm[0])
                method_module = method_module.__name__.split(".")[0] if method_module else ""
                # first condition checks if method have same top module as self.method
                # second condition ignores <lambda>, <genexp>, <listcomp>...
                if method_module == node.top_module and frm.function[0] != "<":
                    context.append(frm.function)
                cls_ = None
                if "self" in frm[0].f_locals:
                    cls_ = frm[0].f_locals["self"].__class__.__name__
                if frm.function == self.root_method.__name__ and cls_ == node.get_method_class(self.root_method):
                    print("found")
                    found = True
                    break
            if found:
                context.reverse()
                between = ".".join(f"{method}" for method in context)
                node.context = node.get_method_class(self.root_method) + ":" + between + "." + node.method.__name__
            else:
                node.context = node.get_method_class(self.root_method) + ":" + node.method.__name__
            print(f"Context found: {node.context}")
        self.insert_into_tree(node)

    def _insert_into_tree(self, node, to_be_parent, parsed_context) -> None:
        for child in to_be_parent.children:
            child_parsed_context = child.context.split(":")[1].split(".")
            max_len = min(len(child_parsed_context), len(parsed_context))
            parsed_context_tmp = parsed_context.copy()
            match = False
            for i in reversed(range(max_len)):
                if child_parsed_context[i] == parsed_context_tmp[i]:
                    match = True
                    _ = child_parsed_context.pop(i)
                    _ = parsed_context_tmp.pop(i)
            if not match:
                continue

            if len(child_parsed_context) and not len(parsed_context_tmp):
                for i in range(len(child.parent.children)):
                    if child.parent.children[i] == child:
                        _ = child.parent.children.pop(i)
                child.parent.children.append(node)
                node.parent = child.parent
                child.parent = node
                node.children.append(child)
                return
            elif not len(child_parsed_context) and len(parsed_context_tmp):
                self._insert_into_tree(node, child, parsed_context)
                return
            else:
                to_be_parent.children.append(node)
                node.parent = to_be_parent
                return
        print(f"appending node: {node.context} to parent: {to_be_parent.context}")
        to_be_parent.children.append(node)
        print(to_be_parent.context)
        node.parent = to_be_parent
        return


class MethodTreeNode(log.InstanceLoggerMixin):
    """
    Tree for storing method calls context
    """

    parent: typing.Optional[MethodTreeNode]
    children: typing.List[MethodTreeNode]
    method: typing.Optional[typing.Callable]

    context: str
    root_context: typing.Optional[str]

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
        self.root_context = None

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
            between = self.get_methods_between(self.method.__name__)
            if between != "":
                child.context = self.context + "." + between + "." + child.context
            else:
                child.context = self.context + "." + child.context
        self.children.append(child)
        self.debug(f"{self.add_child.__qualname__}: node {self.context!r} added child: {child.context!r}")
        return child

    # move to ContextTree
    def insert_into_tree(self, root: MethodTreeNode) -> None:
        # get root context from existing root if exists, else find its own root context(self will be root)
        self.root_context = root.children[0].context if root.children[0] else self.get_method_class(self.method)
        # get context from root.method to self.method
        between = self.get_methods_between(self.root_context)
        self.context = self.root_context + "." + between if between != "" else self.root_context
        self._insert_into_tree(root, self.context.split(":")[1].split("."), 0)

        # TODO: debug log
        # self.debug(f"{self.insert_into_tree.__qualname__}: node {self.context!r} added child: {child.context!r}")

    # move to ContextTree
    def _insert_into_tree(self, to_be_parent, parsed_context) -> None:
        # TODO: DOCSTRING!!!!!
        for child in to_be_parent.children:
            child_parsed_context = child.context.split(":")[1].split(".")
            max_len = min(len(child_parsed_context), len(parsed_context))
            parsed_context_tmp = parsed_context.copy()
            match = False
            for i in reversed(range(max_len)):
                if child_parsed_context[i] == parsed_context_tmp[i]:
                    match = True
                    _ = child_parsed_context.pop(i)
                    _ = parsed_context_tmp.pop(i)
            if not match:
                continue

            if len(child_parsed_context) and not len(parsed_context_tmp):
                for i in range(len(child.parent.children)):
                    if child.parent.children[i] == child:
                        _ = child.parent.children.pop(i)
                child.parent.children.append(self)
                self.parent = child.parent
                child.parent = self
                self.children.append(child)
                return
            elif not len(child_parsed_context) and len(parsed_context_tmp):
                self._insert_into_tree(child, parsed_context)
                return
            else:
                to_be_parent.children.append(self)
                self.parent = to_be_parent
                return

        to_be_parent.children.append(self)
        self.parent = to_be_parent
        return

    def find_in_tree(self):
        pass

    def delete_child(self) -> None:
        """Delete first child of node"""
        try:
            child = self.children.pop(0)
            child.parent = None
            self.debug(f"{self.delete_child.__qualname__}: node {self.context!r} deleted child: {child.context!r}")
        except IndexError:
            self.debug(f"{self.delete_child.__qualname__}: node {self.context!r} do not have any children")

    # move to ContextTree
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

    def get_methods_between(self, method_to: str) -> str:
        """Creates string from methods between `parent.method` and `self.method`

        :returns: Method calling context string. Example: "method1.method2.method3"
        """
        methods_between = []
        starting_method = method_to.split(":")[-1]
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

    # move to ContextTree
    def print_postorder(self):
        for child in self.children:
            child.print_postorder()
        children_context = []
        for child in self.children:
            children_context.append(child.context)
        parent_context = self.parent.context if self.parent and self.parent.context != "" else "root"
        self_context = self.context if self.context != "" else "root"
        print(f"{self_context} with parent {parent_context} " f" and children {children_context}")
