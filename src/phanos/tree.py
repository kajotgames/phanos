from __future__ import annotations

import asyncio
import inspect
import logging
import typing

from . import log


class Context:
    """
    class for keeping and managing one MethodTreeNode context
    """

    # top module of root_method
    top_module: typing.Optional[str]
    context: str
    method: typing.Optional[typing.Callable]
    task_name: typing.Optional[str]

    def __init__(self, method: typing.Optional[typing.Callable] = None):
        """

        :param method: method of MethodTreeNode object
        """
        self.method = method
        self.task_name = None
        if method:
            module = inspect.getmodule(self.method)
            self.context = method.__name__
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
        Gets owner(class or module) name where `self.method` was defined.

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
        """Compose and sets context of `child` object

        Creates string from methods between `self.method` and `child.method`.
        This string is found from current stack.
        Sets `child.context` value as side effect

        :param child: Specific child Context of MethodTreeNode
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

    # TODO: movee or smthing
    @staticmethod
    def get_await_stack(coro):
        """Return a coroutine's chain of awaiters.

        This follows the cr_await links.
        """
        stack = []
        while coro is not None and hasattr(coro, "cr_await"):
            stack.append(coro)
            coro = coro.cr_await
        return stack

    @staticmethod
    def get_task_tree():
        """Return the task tree dict {awaited: awaiting}.
        This follows the _fut_waiter links and constructs a map
        from awaited tasks to the tasks that await them.
        """
        tree = {}
        for task in asyncio.all_tasks():
            awaited = task._fut_waiter
            if awaited is not None:
                tree[awaited] = task
        return tree

    def get_task_stack(self, task):
        """Return the stack of tasks awaiting a task.
        For each task it returns a tuple (task, awaiters) where
        awaiters is the chain of coroutines comprising the task.
        The first entry is the argument task, the last entry is
        the root task (often "Task-1", created by asyncio.run()).
        For example, if we have a task A running a coroutine f1,
        where f1 awaits f2, and f2 awaits a task B running a coroutine
        f3 which awaits f4 which awaits f5, then we'll return
            [
                (B, [f3, f4, f5]),
                (A, [f1, f2]),
            ]
        NOTE: The coroutine stack for the *current* task is inaccessible.
        To work around this, use `await task_stack()`.
        TODO:
        - Maybe it would be nicer to reverse the stack?
        - Classic coroutines and async generators are not supported yet.
        - This is expensive due to the need to first create a reverse
          mapping of awaited tasks to awaiting tasks.
        """

        tree = self.get_task_tree()
        stack = []
        while task is not None:
            coro = task.get_coro()
            awaiters = self.get_await_stack(coro)
            stack.append((task, awaiters))
            task = tree.get(task)
        return stack

    async def task_stack(self, task):
        """Return the stack of tasks awaiting the current task.
        This exists so you can get the coroutine stack for the current task.
        """

        async def helper(task_):
            return self.get_task_stack(task_)

        return await asyncio.create_task(helper(task), name="TaskStackHelper")

    def find_task_context(self, tasks) -> typing.List[str]:
        """Helper to summarize a task stack."""
        coro_stack = []
        for task, awaiters in reversed(tasks):
            for awaiter in awaiters:
                method_module = inspect.getmodule(awaiter.cr_frame)
                method_module = method_module.__name__.split(".")[0] if method_module else ""
                if method_module == self.top_module:
                    coro_stack.append(awaiter.__qualname__)

        return coro_stack

    async def find_context(self, root: MethodTreeNode, active_tasks: typing.List[str]) -> None:
        """Finds context string of self.

        Finds context string for `self.method` from current stack. Iterates over stack until it finds method of
        root context

        :param active_tasks:
        :param root: root node of ContextTree
        """
        root_methods_names = [str(child.ctx).split(":")[1] for child in root.children]
        root_contexts = [str(child.ctx) for child in root.children]
        # if is task, get whole context here, else get it in bottom loop
        stack = []
        for task in asyncio.all_tasks():
            if task.get_name() not in active_tasks and self.method.__qualname__ == task.get_coro().__qualname__:
                active_tasks.append(task.get_name())
                self.task_name = task.get_name()
                tree = await self.task_stack(task)
                stack = self.find_task_context(tree)
                root_idx = None
                for idx, name in enumerate(stack, 0):
                    if name.replace(".", ":") in root_contexts:
                        root_idx = idx
                        break
                self.context = stack[root_idx].split(".")[0] + ":"
                stack = [item.split(".")[1] for item in stack]
                self.context = self.context + ".".join(stack[root_idx:]) + "." + self.method.__name__
                return

        # coroutine
        found_context = []
        found = False
        for frm in inspect.stack():
            method_module = inspect.getmodule(frm[0])
            method_module = method_module.__name__.split(".")[0] if method_module else ""
            # first condition checks if method have same top module as self.method
            # second condition ignores <lambda>, <genexp>, <listcomp>, ...
            if method_module == self.top_module and frm.function[0] != "<":
                found_context.append(frm.function)
                # get class from `frm`
                if frm.function in root_methods_names:
                    cls_ = self.get_class_from_frame(frm.frame)
                    cls_ctx = cls_ + ":" + frm.function
                    if cls_ctx in root_contexts:
                        found_context.reverse()
                        between = ".".join(f"{method}" for method in found_context)
                        self.context = cls_ + ":" + between + "." + self.method.__name__
                        found = True
        if not found:
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
                # TODO: change now when decorator with @wraps can be simplified
                code = fobj.__closure__[0].cell_contents.__code__
                if code == fr.f_code:
                    return fobj.__closure__[0].cell_contents.__qualname__.split(".")[0]

        # function module
        return module.__name__.split(".")[-1] if module else None


class ContextTree(log.InstanceLoggerMixin):
    root: MethodTreeNode
    current_node: MethodTreeNode
    active_tasks: typing.List[str]

    def __init__(self, logger=None):
        super().__init__(logged_name="phanos", logger=logger or logging.getLogger(__name__))
        self.root = MethodTreeNode(logger=self.logger)
        self.current_node = self.root
        self.active_tasks = []

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
                break
        # no complete match -> insert as leaf, `node.parent` will be previous best match (root)
        parent_context = str(root.ctx) if root.ctx.context != "" else "root"
        self.debug(f"appending leaf node: {node.ctx!r} to parent: {parent_context!r}")
        root.children.append(node)
        node.parent = root
        return

    async def find_context_and_insert(self, node: MethodTreeNode) -> None:
        await node.ctx.find_context(self.root, self.active_tasks)
        self.insert(node)

    def delete_node(self, node: MethodTreeNode, root: typing.Optional[MethodTreeNode] = None) -> None:
        # TODO: find timestamp, how to save it
        if root is None:
            root = self.root

        for child in root.children:
            if child is node:
                if node.ctx.task_name is not None and node.ctx.task_name in self.active_tasks:
                    self.active_tasks.remove(node.ctx.task_name)

                node.parent.children.remove(node)
                node.parent.children.extend(node.children)

                for child_to_move in node.children:
                    child_to_move.parent = node.parent

                node.children = []
                node.parent = None

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
