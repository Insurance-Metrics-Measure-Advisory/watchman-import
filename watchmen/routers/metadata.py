# IMPORT data
import logging
from datetime import datetime
from enum import Enum
from typing import List, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from watchmen.auth.storage.user import import_user_to_db, get_user, update_user_storage
from watchmen.auth.storage.user_group import import_user_group_to_db, get_user_group, update_user_group_storage
from watchmen.auth.user_group import UserGroup
from watchmen.common import deps
from watchmen.common.model.user import User
from watchmen.common.snowflake.snowflake import get_surrogate_key
from watchmen.common.utils.data_utils import add_tenant_id_to_model
from watchmen.console_space.model.console_space import ConsoleSpace, ConsoleSpaceSubject
from watchmen.console_space.storage.console_space_storage import load_console_space_by_id, \
    update_console_space, import_console_space_to_db
from watchmen.console_space.storage.console_subject_storage import import_console_subject_to_db, \
    load_console_subject_by_id, update_console_subject
from watchmen.dashborad.model.dashborad import ConsoleDashboard
from watchmen.dashborad.storage.dashborad_storage import import_dashboard_to_db, load_dashboard_by_id, \
    update_dashboard_to_storage
from watchmen.pipeline.model.pipeline import Pipeline
from watchmen.pipeline.storage.pipeline_storage import import_pipeline_to_db, load_pipeline_by_id, update_pipeline
from watchmen.report.model.report import Report
from watchmen.report.storage.report_storage import import_report_to_db, load_report_by_id, save_subject_report
from watchmen.space.service.admin import update_space_by_id
from watchmen.space.space import Space
from watchmen.space.storage.space_storage import import_space_to_db, get_space_by_id
from watchmen.topic.service.topic_service import update_topic_schema, create_topic_schema
from watchmen.topic.storage.topic_schema_storage import get_topic_by_id, import_topic_to_db
from watchmen.topic.topic import Topic

router = APIRouter()

log = logging.getLogger("app." + __name__)


class ImportCheckResult(BaseModel):
    topicId: str = None
    reason: str = None
    pipelineId: str = None
    spaceId: str = None
    connectionId: str = None


class ImportDataResponse(BaseModel):
    passed: bool = None
    topics: List[ImportCheckResult] = []
    pipelines: List[ImportCheckResult] = []
    spaces: List[ImportCheckResult] = []
    connectedSpaces: List[ImportCheckResult] = []


class ImportDataRequest(BaseModel):
    topics: List[Topic] = []
    pipelines: List[Pipeline] = []
    spaces: List[Space] = []
    connectedSpaces: List[ConsoleSpace] = []
    importType: str = None


class ImportTPSCSType(Enum):
    NON_REDUNDANT = 'non-redundant'
    REPLACE = 'replace'
    FORCE_NEW = 'force-new'


### import space

@router.post("/import/admin/user", tags=["import"])
async def import_user(user: User):
    result = get_user(user.userId)
    if result is None:
        import_user_to_db(user)
    else:
        update_user_storage(user)


# import user group


@router.post("/import/admin/user/group", tags=["import"])
async def import_user_group(group: UserGroup, current_user: User = Depends(deps.get_current_user)):
    result = get_user_group(group.userGroupId, current_user)
    group = add_tenant_id_to_model(group, current_user)
    if result is None:
        import_user_group_to_db(group)
    else:
        update_user_group_storage(group)


# import space

def __is_same_tenant(tenant_id, current_user):
    return tenant_id == current_user.tenantId


@router.post("/import/admin/space", tags=["import"])
async def import_space(space: Space, import_type="non-redundant", current_user: User = Depends(deps.get_current_user)):
    if __is_same_tenant(space.tenantId, current_user):
        result = get_space_by_id(space.spaceId, current_user)
        if import_type == ImportTPSCSType.NON_REDUNDANT.value:
            if result is None:
                import_space_to_db(space)
            else:
                raise Exception("duplicate space found")
        elif import_type == ImportTPSCSType.REPLACE.value:

            update_space_by_id(space.spaceId, space)
        else:
            space.spaceId = get_surrogate_key()
            import_space_to_db(space)
    else:
        if import_type == ImportTPSCSType.FORCE_NEW.value:
            space = add_tenant_id_to_model(space, current_user)
            space.spaceId = get_surrogate_key()
            import_space_to_db(space)


## import topic data
@router.post("/import/admin/topic", tags=["import"])
async def import_topic(topic: Topic, current_user: User = Depends(deps.get_current_user)):
    result = get_topic_by_id(topic.topicId, current_user)
    topic = add_tenant_id_to_model(topic, current_user)
    if result is None:
        return create_topic_schema(topic)
    else:
        return update_topic_schema(topic.topicId, topic)


## import pipeline data

@router.post("/import/admin/pipeline", tags=["import"])
async def import_pipeline(pipeline: Pipeline, current_user: User = Depends(deps.get_current_user)):
    result = load_pipeline_by_id(pipeline.pipelineId, current_user)
    pipeline = add_tenant_id_to_model(pipeline, current_user)
    if result is None:
        return import_pipeline_to_db(pipeline)
    else:
        return update_pipeline(pipeline)


## import connect space
@router.post("/import/console/space", tags=["import"])
async def import_console_space(console_space: ConsoleSpace, current_user: User = Depends(deps.get_current_user)):
    result = load_console_space_by_id(console_space.connectId, current_user)
    console_space = add_tenant_id_to_model(console_space, current_user)
    if result is None:
        import_console_space_to_db(console_space)
    else:
        update_console_space(console_space)


## import dataset
@router.post("/import/console/space/subject", tags=["import"])
async def import_console_subject(subject: ConsoleSpaceSubject, current_user: User = Depends(deps.get_current_user)):
    result = load_console_subject_by_id(subject.subjectId, current_user)
    subject = add_tenant_id_to_model(subject, current_user)
    if result is None:
        import_console_subject_to_db(subject)
    else:
        update_console_subject(subject)


## import report

@router.post("/import/console/report", tags=["import"])
async def import_console_report(report: Report, current_user: User = Depends(deps.get_current_user)):
    result = load_report_by_id(report.reportId, current_user)
    report = add_tenant_id_to_model(report, current_user)
    if result is None:
        import_report_to_db(report)
    else:
        save_subject_report(report)


## import dashborad
@router.post("/import/console/dashboard", tags=["import"])
async def import_dashboard(dashboard: ConsoleDashboard, current_user: User = Depends(deps.get_current_user)):
    result = load_dashboard_by_id(dashboard.dashboardId, current_user)
    dashboard = add_tenant_id_to_model(dashboard, current_user)
    if result is None:
        import_dashboard_to_db(dashboard)
    else:
        update_dashboard_to_storage(dashboard)


def __update_create_time(model: Any):
    model.createTime = datetime.now().replace(tzinfo=None).isoformat()
    return model


def __update_last_modified(model: Any):
    model.lastModified = datetime.now().replace(tzinfo=None)
    return model


def __clear_datasource_id(topic: Topic):
    topic.dataSourceId = None
    return topic


def __process_non_redundant_import(import_request: ImportDataRequest, current_user) -> ImportDataResponse:
    import_response = ImportDataResponse()
    for topic in import_request.topics:
        result_topic = get_topic_by_id(topic.topicId, current_user)
        topic = add_tenant_id_to_model(topic, current_user)

        if result_topic:
            import_response.topics.append(
                ImportCheckResult(topicId=result_topic.topicId, reason="topic alredy existed"))
        else:
            __clear_datasource_id(topic)
            import_topic_to_db(__update_create_time(__update_last_modified(topic)))

    for pipeline in import_request.pipelines:
        result_pipeline = load_pipeline_by_id(pipeline.pipelineId, current_user)
        pipeline = add_tenant_id_to_model(pipeline, current_user)

        if result_pipeline:
            import_response.pipelines.append(
                ImportCheckResult(pipelineId=result_pipeline.pipelineId, reason="pipeline alredy existed"))
        else:
            return import_pipeline_to_db(__update_create_time(__update_last_modified(pipeline)))

    for space in import_request.spaces:
        result_space = get_space_by_id(space.spaceId, current_user)
        space = add_tenant_id_to_model(space, current_user)
        if result_space:
            import_response.spaces.append(
                ImportCheckResult(spaceId=result_space.spaceId, reason="space alredy existed"))
        else:
            import_space_to_db(__update_create_time(__update_last_modified(space)))

    for console_space in import_request.connectedSpaces:
        result_connect_space = load_console_space_by_id(console_space.connectId, current_user)
        console_space = add_tenant_id_to_model(console_space, current_user)
        if result_connect_space:
            import_response.connectedSpaces.append(
                ImportCheckResult(connectId=result_connect_space.connectId, reason="connect_space alredy existed"))

        else:
            __create_console_space_to_db(__update_create_time(__update_last_modified(console_space)))

    return import_response


def __update_console_space_to_db(console_space: ConsoleSpace, current_user):
    for console_space_subject in console_space.subjects:
        console_space_subject = add_tenant_id_to_model(console_space_subject, current_user)
        console_space.subjectIds.append(console_space_subject.subjectId)
        for report in console_space_subject.reports:
            console_space_subject.reportIds.append(report.reportId)
            save_subject_report(__update_last_modified(report))
        update_console_subject(__update_last_modified(console_space_subject))
    update_console_space(console_space)


def __create_console_space_to_db(console_space: ConsoleSpace, current_user):
    for console_space_subject in console_space.subjects:
        console_space_subject = add_tenant_id_to_model(console_space_subject, current_user)
        console_space.subjectIds.append(console_space_subject.subjectId)
        for report in console_space_subject.reports:
            console_space_subject.reportIds.append(report.reportId)
            import_report_to_db(__update_create_time(__update_last_modified(report)))
        import_console_subject_to_db(__update_create_time(__update_last_modified(console_space_subject)))
    import_console_space_to_db(console_space)


def __process_replace_import(import_request: ImportDataRequest, current_user):
    import_response = ImportDataResponse()
    for topic in import_request.topics:
        result_topic = get_topic_by_id(topic.topicId, current_user)
        topic = add_tenant_id_to_model(topic, current_user)
        if result_topic:
            topic.dataSourceId = result_topic.dataSourceId
            update_topic_schema(topic.topicId, __update_last_modified(topic))
        else:
            __clear_datasource_id(topic)
            import_topic_to_db(__update_create_time(__update_last_modified(topic)))

    for pipeline in import_request.pipelines:
        result_pipeline = load_pipeline_by_id(pipeline.pipelineId, current_user)
        pipeline = add_tenant_id_to_model(pipeline, current_user)
        if result_pipeline:
            update_pipeline(__update_last_modified(pipeline))
        else:
            import_pipeline_to_db(__update_create_time(__update_last_modified(pipeline)))

    for space in import_request.spaces:
        result_space = get_space_by_id(space.spaceId, current_user)
        space = add_tenant_id_to_model(space, current_user)
        if result_space:
            update_space_by_id(space.spaceId, __update_last_modified(space))
        else:
            import_space_to_db(__update_create_time(__update_last_modified(space)))

    for console_space in import_request.connectedSpaces:
        result_connect_space = load_console_space_by_id(console_space.connectId, current_user)
        console_space = add_tenant_id_to_model(console_space, current_user)
        if result_connect_space:
            __update_console_space_to_db(__update_last_modified(console_space))
        else:
            __create_console_space_to_db(__update_create_time(__update_last_modified(console_space)))
    return import_response


def __process_forced_new_import(import_request: ImportDataRequest, current_user):
    ## TODO __process_forced_new_import
    pass


@router.post("/import", tags=["import"])
async def import_assert(import_request: ImportDataRequest,
                        current_user: User = Depends(deps.get_current_user)) -> ImportDataResponse:
    if import_request.importType == ImportTPSCSType.NON_REDUNDANT.value:
        log.info("import asset with NON_REDUNDANT type")
        return __process_non_redundant_import(import_request, current_user)
    elif import_request.importType == ImportTPSCSType.REPLACE.value:
        log.info("import asset with replace type")
        return __process_replace_import(import_request, current_user)
    elif import_request.importType == ImportTPSCSType.FORCE_NEW.value:
        pass
    else:
        raise Exception("unknown import type {0}".format(import_request.importType))
