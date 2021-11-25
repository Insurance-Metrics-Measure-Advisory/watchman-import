import logging

from distributed import as_completed

from watchmen.config.config import settings
from watchmen.monitor.model.pipeline_monitor import UnitRunStatus
from watchmen.pipeline.core.context.action_context import ActionContext
from watchmen.pipeline.core.context.unit_context import UnitContext
from watchmen.pipeline.core.parameter.parse_parameter import parse_parameter_joint
from watchmen.pipeline.core.worker.action_worker import run_action

log = logging.getLogger("app." + __name__)


def should_run(unit_context: UnitContext, unit_run_status: UnitRunStatus) -> bool:
    unit = unit_context.unit
    if unit.on is None:
        unit_run_status.conditionResult = True
        return True
    current_data = unit_context.stageContext.pipelineContext.currentOfTriggerData
    variables = unit_context.stageContext.pipelineContext.variables
    condition_result = parse_parameter_joint(unit.on, current_data, variables)
    unit_run_status.conditionResult = condition_result
    return condition_result


def run_unit(unit_context: UnitContext):
    loop_variable_name = unit_context.unit.loopVariableName
    if loop_variable_name is not None and loop_variable_name != "":
        loop_variable = unit_context.stageContext.pipelineContext.variables[loop_variable_name]
        if isinstance(loop_variable, list):
            if settings.DASK_ON:
                run_loop_with_dask(loop_variable_name, unit_context)
            else:
                run_loop_actions(loop_variable_name, unit_context)
        elif loop_variable is not None:  # the loop variable just have one element.
            unit_run_status = UnitRunStatus()
            if unit_context.unit.do is not None:
                unit_context.unitStatus = UnitRunStatus()
                unit_context.unitStatus.unitId = unit_context.unit.unitId
                if should_run(unit_context, unit_run_status):
                    unit_context.unitStatus.name = unit_context.unit.name
                    for action in unit_context.unit.do:
                        action_context = ActionContext(unit_context, action)
                        action_context.delegateVariableName = loop_variable_name
                        action_context.delegateValue = loop_variable
                        result, trigger_pipeline_data_list = run_action(action_context)
                        if trigger_pipeline_data_list:
                            unit_context.stageContext.pipelineContext.pipeline_trigger_merge_list = [
                                *action_context.unitContext.stageContext.pipelineContext.pipeline_trigger_merge_list,
                                *trigger_pipeline_data_list]
                        unit_context.unitStatus.actions.append(result.actionStatus)
                unit_context.stageContext.stageStatus.units.append(unit_context.unitStatus)
    else:
        if unit_context.unit.do is not None:
            unit_context.unitStatus = UnitRunStatus()
            unit_context.unitStatus.unitId = unit_context.unit.unitId
            if should_run(unit_context, unit_context.unitStatus):
                for action in unit_context.unit.do:
                    action_context = ActionContext(unit_context, action)
                    result, trigger_pipeline_data_list = run_action(action_context)
                    if trigger_pipeline_data_list:
                        unit_context.stageContext.pipelineContext.pipeline_trigger_merge_list = [
                            *action_context.unitContext.stageContext.pipelineContext.pipeline_trigger_merge_list,
                            *trigger_pipeline_data_list]
                    unit_context.unitStatus.actions.append(result.actionStatus)
            unit_context.stageContext.stageStatus.units.append(unit_context.unitStatus)


def run_loop_actions(loop_variable_name, unit_context):
    for value in unit_context.stageContext.pipelineContext.variables[loop_variable_name]:
        unit_run_status = UnitRunStatus()
        unit_run_status.unitId = unit_context.unit.unitId
        if unit_context.unit.do is not None:
            if should_run(unit_context, unit_run_status):
                for action in unit_context.unit.do:
                    action_context = ActionContext(unit_context, action)
                    action_context.delegateVariableName = loop_variable_name
                    action_context.delegateValue = value
                    result, trigger_pipeline_data_list = run_action(action_context)
                    if trigger_pipeline_data_list:
                        unit_context.stageContext.pipelineContext.pipeline_trigger_merge_list = [
                            *action_context.unitContext.stageContext.pipelineContext.pipeline_trigger_merge_list,
                            *trigger_pipeline_data_list]
                    unit_run_status.actions.append(result.actionStatus)
                unit_context.unitStatus = unit_run_status
        unit_context.stageContext.stageStatus.units.append(unit_context.unitStatus)


def run_loop_with_dask(loop_variable_name, unit_context, unit_run_status):
    from watchmen.common.dask.client import get_dask_client
    futures = []
    for value in unit_context.stageContext.pipelineContext.variables[loop_variable_name]:
        if unit_context.unit.do is not None:
            if should_run(unit_context, unit_run_status):
                unit_context.unitStatus = UnitRunStatus()
                unit_context.unitStatus.unitId = unit_context.unit.unitId
                for action in unit_context.unit.do:
                    action_context = ActionContext(unit_context, action)
                    action_context.delegateVariableName = loop_variable_name
                    action_context.delegateValue = value
                    futures.append(get_dask_client().submit(run_action, action_context))
    for future in as_completed(futures):
        result, trigger_pipeline_data_list = future.result()
        if trigger_pipeline_data_list:
            unit_context.stageContext.pipelineContext.pipeline_trigger_merge_list = [
                *action_context.unitContext.stageContext.pipelineContext.pipeline_trigger_merge_list,
                *trigger_pipeline_data_list]
        unit_context.unitStatus.actions.append(result.actionStatus)
