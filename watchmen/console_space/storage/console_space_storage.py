from typing import List

from watchmen.auth.user import User
from watchmen.common.snowflake.snowflake import get_surrogate_key
from watchmen.common.utils.data_utils import check_fake_id
from watchmen.console_space.model.connect_space_graphics import ConnectedSpaceGraphics
from watchmen.console_space.model.console_space import ConsoleSpace
from watchmen.database.storage.storage_template import insert_one, update_one_first, find_one, list_, find_, \
    delete_by_id


# template = find_template()


def create_console_space(console_space: ConsoleSpace):
    # return template.create("console_spaces", console_space, ConsoleSpace)
    return insert_one(console_space, ConsoleSpace, "console_spaces")


def update_console_space(console_space: ConsoleSpace):
    # return template.update_one("console_spaces", {"connectId": console_space.connectId}, console_space, ConsoleSpace)
    return update_one_first({"connectId": console_space.connectId}, console_space, ConsoleSpace, "console_spaces")


def save_console_space(console_space: ConsoleSpace) -> ConsoleSpace:
    if console_space.connectId is None or check_fake_id(console_space.connectId):
        console_space.connectId = get_surrogate_key()
        return create_console_space(console_space)
    else:
        return update_console_space(console_space)


def load_console_space_by_id(connect_id: str, current_user) -> ConsoleSpace:
    return find_one({"and": [{"connectId": connect_id}, {"tenantId": current_user.tenantId}]}, ConsoleSpace,
                    "console_spaces")


def delete_console_space_storage(connect_id: str):
    # template.delete_one("console_spaces", {"connectId": connect_id})
    delete_by_id(connect_id, "console_spaces")


def load_console_space_list_by_user(user_id: str, current_user: User) -> ConsoleSpace:
    # return template.find("console_spaces", {"userId": user_id}, ConsoleSpace)
    return find_({"and": [{"userId": user_id}, {"tenantId": current_user.tenantId}]}, ConsoleSpace, "console_spaces")


def load_console_space_by_subject_id(subject_id: str, current_user) -> ConsoleSpace:
    # return template.find_one("console_spaces", {"subjectIds": subject_id}, ConsoleSpace)
    return find_one({"and": [{"subjectIds": {"in": [subject_id]}}, {"tenantId": current_user.tenantId}]}, ConsoleSpace,
                    "console_spaces")


def rename_console_space_by_id(connect_id: str, name: str) -> ConsoleSpace:
    # return template.update_one("console_spaces", {"connectId": connect_id}, {"name": name}, ConsoleSpace)
    return update_one_first({"connectId": connect_id}, {"name": name}, ConsoleSpace, "console_spaces")


def create_console_space_graph(console_space_graph: ConnectedSpaceGraphics) -> ConnectedSpaceGraphics:
    # return template.create("console_space_graph", console_space_graph, ConnectedSpaceGraphics)
    return insert_one(console_space_graph, ConnectedSpaceGraphics, "console_space_graph")


def update_console_space_graph(console_space_graph: ConnectedSpaceGraphics) -> ConnectedSpaceGraphics:
    '''
    return template.update_one("console_space_graph", {"connectId": console_space_graph.connectId}, console_space_graph,
                               ConnectedSpaceGraphics)
    '''
    return update_one_first({"connectId": console_space_graph.connectId}, console_space_graph, ConnectedSpaceGraphics,
                            "console_space_graph")


def load_console_space_graph_by_user_id(user_id: str, current_user) -> List[ConnectedSpaceGraphics]:
    # return template.find("console_space_graph", {"userId": user_id}, ConnectedSpaceGraphics)
    return list_({"and": [{"userId": user_id}, {"tenantId": current_user.tenantId}]}, ConnectedSpaceGraphics,
                 "console_space_graph")


def load_console_space_graph(connect_id: str, current_user) -> ConnectedSpaceGraphics:
    # return template.find_one("console_space_graph", {"connectId": connect_id}, ConnectedSpaceGraphics)
    return find_one({"and": [{"connectId": connect_id}, {"tenantId": current_user.tenantId}]}, ConnectedSpaceGraphics,
                    "console_space_graph")


def import_console_spaces(console_space: ConnectedSpaceGraphics) -> ConnectedSpaceGraphics:
    # return template.create("console_space_graph", console_space, ConnectedSpaceGraphics)
    return insert_one(console_space, ConnectedSpaceGraphics, "console_space_graph")
