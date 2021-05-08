import logging
import statistics
from functools import reduce

import numpy as np
import pandas as pd

from watchmen.common.constants import pipeline_constants, parameter_constants
from watchmen.common.constants.pipeline_constants import VALUE
from watchmen.common.utils.condition_result import ConditionResult
from watchmen.pipeline.model.pipeline import ParameterJoint, Parameter, Conditional
from watchmen.pipeline.single.stage.unit.utils.units_func import get_value, get_factor, process_variable, \
    check_condition, convert_factor_type, __split_value, SPLIT_FLAG, MEMORY, SNOWFLAKE, convert_datetime
from watchmen.plugin.service.plugin_service import run_plugin
from watchmen.topic.factor.factor import Factor
from watchmen.topic.topic import Topic

DOT = "."

log = logging.getLogger("app." + __name__)

NONE = 'none'

YEAR_OF = 'year-of'
HALF_YEAR_OF = 'half-year-of'
QUARTER_OF = 'quarter-of'
MONTH_OF = 'month-of'
WEEK_OF_YEAR = 'week-of-year'
WEEK_OF_MONTH = 'week-of-month'
DAY_OF_MONTH = 'day-of-month'
DAY_OF_WEEK = 'day-of-week'

ADD = 'add'
SUBTRACT = 'subtract'
MULTIPLY = 'multiply'
DIVIDE = 'divide'
MODULUS = 'modulus'

COUNT = 'count',
SUM = 'sum',
AVG = 'avg',
MAX = 'max',
MIN = 'min',
MEDIAN = 'med'

DATE_FUNC = [YEAR_OF, HALF_YEAR_OF, QUARTER_OF, MONTH_OF, WEEK_OF_YEAR, WEEK_OF_MONTH, DAY_OF_WEEK, DAY_OF_MONTH]

CALC_FUNC = [ADD, SUBTRACT, MULTIPLY, DIVIDE, MODULUS]


def build_factor_list(factor):
    factor_name_list = factor.name.split(".")
    factor_list = []
    for name in factor_name_list:
        factor = Factor()
        factor.name = name
        factor_list.append(factor)
    return factor_list


def __run_arithmetic(arithmetic, value):
    # print("arithmetic {0} value {1}".format(arithmetic,value))
    if arithmetic is None or arithmetic == NONE or type(value) != list:
        return value
    elif arithmetic == SUM:
        return sum(value)
    elif arithmetic == AVG:
        return statistics.mean(value)
    elif arithmetic == MAX:
        return max(value)
    elif arithmetic == MIN:
        return min(value)
    elif arithmetic == MEDIAN:
        return statistics.median(value)


def run_arithmetic_value_list(arithmetic, value_list):
    if type(value_list) == list:
        results = []
        for source_value in value_list:
            results.append(__run_arithmetic(arithmetic, source_value))
        return results
    else:
        return __run_arithmetic(arithmetic, value_list)


def __process_factor_type(target_factor, source_value_list):
    results = []
    if source_value_list is not None:
        if type(source_value_list) == list:
            for source_value in source_value_list:
                if source_value is not None:
                    result = run_plugin(target_factor.type, source_value)
                    if result is not None:
                        results.append(result)
            return results
        else:
            return run_plugin(target_factor.type, source_value_list)


def __convert_to_target_value_list(target_factor, source_value_list):
    if isinstance(source_value_list, list):
        target_value_list = []
        for source_value in source_value_list:
            target_value_list.append(convert_factor_type(source_value, target_factor.type))
        return target_value_list
    else:
        return convert_factor_type(source_value_list, target_factor.type)


def run_mapping_rules(mapping_list, target_topic, raw_data, pipeline_topic, context=None):
    mapping_results = []

    for mapping in mapping_list:
        source = mapping.source

        target_factor = get_factor(mapping.factorId, target_topic)
        source_value_list = run_arithmetic_value_list(mapping.arithmetic,
                                                      get_source_value_list(pipeline_topic, raw_data, source,
                                                                            target_factor, context))

        target_value_list = __convert_to_target_value_list(target_factor, source_value_list)
        result = __process_factor_type(target_factor, source_value_list)
        merge_plugin_results(mapping_results, result)
        mapping_results.append({target_factor.name: target_value_list})

    mapping_data_list = merge_mapping_data(mapping_results)
    return mapping_data_list


def merge_plugin_results(mapping_results, result):
    if result is not None and len(result) > 0:
        mapping_results.append(result[0])


def __is_date_func(source_type):
    return source_type in DATE_FUNC


def __week_number_of_month(date_value):
    return date_value.isocalendar()[1] - date_value.replace(day=1).isocalendar()[1] + 1


def __process_date_func(source, value):
    log.info("source type {0}  value : {1}".format(source.type, value))

    arithmetic = source.type
    if arithmetic == NONE:
        return value
    elif arithmetic == YEAR_OF:
        return convert_datetime(value).year
    elif arithmetic == MONTH_OF:
        return convert_datetime(value).month
    elif arithmetic == WEEK_OF_YEAR:
        return convert_datetime(value).isocalendar()[1]
    elif arithmetic == DAY_OF_WEEK:
        return convert_datetime(value).weekday()
    elif arithmetic == WEEK_OF_MONTH:
        return __week_number_of_month(convert_datetime(value).date())
    elif arithmetic == QUARTER_OF:
        quarter = pd.Timestamp(convert_datetime(value)).quarter
        return quarter
    elif arithmetic == HALF_YEAR_OF:
        month = convert_datetime(value).month
        if month <= 6:
            return 1
        else:
            return 2
    elif arithmetic == DAY_OF_MONTH:
        days_in_month = pd.Timestamp(convert_datetime(value)).days_in_month
        return days_in_month
    else:
        raise ValueError("unknown arithmetic type {0}".format(arithmetic))


def __is_calculation_operation(source_type):
    return source_type in CALC_FUNC


def __get_operator(source_type):
    if source_type == ADD:
        return np.add
    elif source_type == SUBTRACT:
        return np.subtract
    elif source_type == MULTIPLY:
        return np.multiply
    elif source_type == DIVIDE:
        return np.divide
    elif source_type == MODULUS:
        return np.mod
    else:
        raise Exception("unknown source_type {0}".format(source_type))


def __process_operator(operator, value_list):
    result = reduce(operator, value_list)
    return result


def __process_compute_kind(source: Parameter, raw_data, pipeline_topic, target_factor=None):
    if __is_date_func(source.type):
        value_list = get_source_value_list(pipeline_topic, raw_data, Parameter.parse_obj(source.parameters[0]),
                                           target_factor)
        if type(value_list) == list:
            result = []
            for value in value_list:
                result.append(__process_date_func(source, value))
            return result
        else:
            return __process_date_func(source, value_list)
    elif __is_calculation_operation(source.type):
        operator = __get_operator(source.type)
        value_list = []
        for parameter in source.parameters:
            value = get_source_value_list(pipeline_topic, raw_data, Parameter.parse_obj(parameter), target_factor)
            if type(value) is list:
                value_list.append(np.array(value))
            else:
                value_list.append(value)
        return __process_operator(operator, value_list)


def get_source_value_list(pipeline_topic, raw_data, parameter: Parameter, target_factor: Factor = None, context=None):
    if parameter.kind == parameter_constants.TOPIC:
        source_factor: Factor = get_factor(parameter.factorId, pipeline_topic)
        return get_source_factor_value(raw_data, source_factor)
    elif parameter.kind == parameter_constants.CONSTANT:
        if parameter.value is None or not parameter.value:
            return None
        else:
            variable_type, context_target_name = process_variable(parameter.value)
            if variable_type == MEMORY:
                if context_target_name in context:
                    result = context[context_target_name]
                    if result is None:
                        return __check_default_value(target_factor)
                    else:
                        return result
                else:
                    return __check_default_value(target_factor)
            elif variable_type == SNOWFLAKE:
                return context_target_name
            else:
                if target_factor is not None:
                    if SPLIT_FLAG in parameter.value:
                        value_list = __split_value(parameter.value)
                        result = []
                        for value in value_list:
                            result.append(convert_factor_type(value, target_factor.type))
                        return result
                    else:
                        return convert_factor_type(parameter.value, target_factor.type)
                else:
                    return parameter.value
            # else:
            #
    elif parameter.kind == parameter_constants.COMPUTED:
        print(target_factor.name)
        return __process_compute_kind(parameter, raw_data, pipeline_topic, target_factor)
    else:
        raise Exception("Unknown source kind {0}".format(parameter.kind))


def __check_default_value(target_factor):
    if target_factor is not None and target_factor.defaultValue is not None:
        return convert_factor_type(target_factor.defaultValue, target_factor.type)
    else:
        return None


def get_source_factor_value(raw_data, source_factor):
    if is_sub_field(source_factor):
        results = []
        factor_list = build_factor_list(source_factor)
        source_value_list = get_factor_value(0, factor_list, raw_data, results)
        if len(source_value_list) == 1:
            return source_value_list[0]
        else:
            return source_value_list
    else:
        source_value_list = get_value(source_factor, raw_data)
    return source_value_list


def merge_mapping_data(mapping_results):
    max_value_size = get_max_value_size(mapping_results)
    mapping_data_list = []

    # print("mapping_results", mapping_results)
    # print("max_value_size",max_value_size)
    for i in range(max_value_size):
        mapping_data = {}
        for mapping_result in mapping_results:
            for key, value in mapping_result.items():
                if type(value) is list and len(value) > 0:
                    mapping_data[key] = value[i]
                else:
                    mapping_data[key] = value
        mapping_data_list.append(mapping_data)
    return mapping_data_list


def get_max_value_size(mapping_results):
    index = 0
    for mapping_result in mapping_results:
        for key, value in mapping_result.items():
            if type(value) is list:
                if len(value) > index:
                    return len(value)
                    # print("index",index)
            else:
                return 1
    return index


def is_sub_field(factor):
    return DOT in factor.name


def get_factor_value(index, factor_list, raw_data, result):
    # results=[]
    factor = factor_list[index]
    data = get_value(factor, raw_data)
    if type(data) is list:
        for raw in data:
            get_factor_value(index + 1, factor_list, raw, result)
    elif type(data) is dict:
        get_factor_value(index + 1, factor_list, data, result)
    else:
        if data is None and factor.defaultValue is not None:
            result.append(convert_factor_type(factor.defaultValue, factor.type))
        else:
            result.append(data)

    return result


def __is_current_topic(parameter: Parameter, pipeline_topic: Topic):
    if parameter.kind == parameter_constants.TOPIC and parameter.topicId == pipeline_topic.topicId:
        return True
    else:
        return False


def __get_source_and_target_parameter(condition, pipeline_topic: Topic):
    if __is_current_topic(condition.left, pipeline_topic):
        return condition.left, condition.right
    elif __is_current_topic(condition.right, pipeline_topic):
        return condition.right, condition.left
    else:
        return None, None


def __process_parameter_constants(parameter: Parameter, context, target_factor=None):
    variable_type, context_target_name = process_variable(parameter.value)
    if variable_type == parameter_constants.CONSTANT:
        if target_factor is not None:
            if SPLIT_FLAG in parameter.value:
                value_list = __split_value(parameter.value)
                result = []
                for value in value_list:
                    result.append(convert_factor_type(value, target_factor.type))
                return result
            else:
                return convert_factor_type(parameter.value, target_factor.type)
        else:
            return parameter.value

    elif variable_type == parameter_constants.MEMORY:
        if context_target_name in context:
            return context[context_target_name]
        else:
            raise ValueError("no variable {0} in context".format(context_target_name))
    else:
        raise ValueError("variable_type is invalid")


def __get_factor_for_condition(parameter, pipeline_topic, target_topic):
    if parameter.kind == parameter_constants.TOPIC:
        if __is_current_topic(parameter, pipeline_topic):
            return get_factor(parameter.factorId, pipeline_topic)
        elif __is_current_topic(parameter, target_topic):
            return get_factor(parameter.factorId, target_topic)


def build_parameter_condition(parameter: Parameter, pipeline_topic: Topic, target_topic: Topic, raw_data, context,
                              type_factor=None):
    if parameter.kind == parameter_constants.TOPIC:
        if __is_current_topic(parameter, pipeline_topic):
            return {pipeline_constants.VALUE: get_source_value_list(pipeline_topic, raw_data, parameter)}
        elif __is_current_topic(parameter, target_topic):
            target_factor = get_factor(parameter.factorId, target_topic)
            return {pipeline_constants.NAME: target_factor}
    elif parameter.kind == parameter_constants.CONSTANT:
        return {pipeline_constants.VALUE: __process_parameter_constants(parameter, context, type_factor)}
    elif parameter.kind == parameter_constants.COMPUTED:
        if __is_date_func(parameter.type):
            return {pipeline_constants.VALUE: __process_compute_date(parameter, pipeline_topic, raw_data)}
        elif __is_calculation_operation(parameter.type):
            return __process_compute_calculation_condition(parameter, pipeline_topic, target_topic, raw_data, context)
    else:
        raise Exception("Unknown parameter kind {0}".format(parameter.kind))


def __process_compute_calculation_condition(parameter, pipeline_topic, target_topic, raw_data, context):
    operator = __get_operator(parameter.type)
    value_list = []
    for parameter in parameter.parameters:
        parameter_result = build_parameter_condition(parameter, pipeline_topic, target_topic, raw_data, context)
        if pipeline_constants.VALUE in parameter_result:
            value = parameter_result[pipeline_constants.VALUE]
            if type(value) is list:
                value_list.append(np.array(value))
            else:
                value_list.append(value)
        if pipeline_constants.NAME in parameter_result:
            raise Exception("target_topic in compute parameter is not supported")

    return __process_operator(operator, value_list)


def __process_compute_date(parameter, pipeline_topic, raw_data):
    value_list = get_source_value_list(pipeline_topic, raw_data, Parameter.parse_obj(parameter.parameters[0]))
    if type(value_list) == list:
        result = []
        for value in value_list:
            result.append(__process_date_func(parameter, value))
        return result
    else:
        return __process_date_func(parameter, value_list)


def __process_condition(condition, pipeline_topic, target_topic, raw_data, context):
    where = {pipeline_constants.OPERATOR: condition.operator}
    factor = __get_factor_for_condition(condition.left, pipeline_topic, target_topic)
    process_parameter_result(build_parameter_condition(condition.left, pipeline_topic, target_topic, raw_data, context),
                             where)
    process_parameter_result(
        build_parameter_condition(condition.right, pipeline_topic, target_topic, raw_data, context, factor), where)
    return where


def process_parameter_result(right_result, where):
    if pipeline_constants.NAME in right_result:
        where[pipeline_constants.NAME] = right_result[pipeline_constants.NAME]
    else:
        where[pipeline_constants.VALUE] = right_result[pipeline_constants.VALUE]


def build_query_conditions(conditions: ParameterJoint, pipeline_topic: Topic, raw_data, target_topic, context):
    if len(conditions.filters) == 1:
        # ignore jointType
        condition = conditions.filters[0]
        return None, __process_condition(condition, pipeline_topic, target_topic, raw_data, context)
    else:
        where_conditions = []
        for condition in conditions.filters:
            if condition.jointType is None:
                where_conditions.append(__process_condition(condition, pipeline_topic, target_topic, raw_data, context))
            else:
                where_conditions.append(
                    build_query_conditions(condition, pipeline_topic, target_topic, raw_data, context))

        return conditions.jointType, where_conditions


def __convert_to_list(value):
    if type(value) == list:
        return value
    else:
        # TODO for in and not in operator
        pass


def __get_condition_factor(parameter: Parameter, topic):
    if parameter.kind == parameter_constants.TOPIC:
        return get_factor(parameter.factorId, topic)


def __build_on_condition(parameter_joint: ParameterJoint, topic, data, context):
    if parameter_joint.filters:
        joint_type = parameter_joint.jointType
        condition_result = ConditionResult(logicOperator=joint_type)
        for filter_condition in parameter_joint.filters:
            if filter_condition.jointType is not None:
                condition_result.resultList.append(__build_on_condition(filter_condition, topic, data, context))
            else:
                left_value_list = get_source_value_list(topic, data, filter_condition.left, target_factor=None,
                                                        context=context)
                log.info("left_value_list:{0}".format(left_value_list))
                factor = __get_condition_factor(filter_condition.left, topic)
                right_value_list = get_source_value_list(topic, data, filter_condition.right,
                                                         factor, context)
                log.info("right_value_list:{0}".format(right_value_list))
                result: bool = check_condition(filter_condition.operator, left_value_list, right_value_list)
                condition_result.resultList.append(result)
        log.info("condition_result:{0}".format(condition_result))
        return condition_result


def __check_on_condition(match_result: ConditionResult) -> bool:
    if match_result is None or match_result.logicOperator is None:
        return True
    elif match_result.logicOperator == "and":
        result = True
        for result in match_result.resultList:
            if type(result) == ConditionResult:
                if not __check_on_condition(result):
                    result = False
            else:
                if not result:
                    result = False
        return result
    elif match_result.logicOperator == "or":
        for result in match_result.resultList:
            if type(result) == ConditionResult:
                if __check_on_condition(result):
                    return True
            else:
                if result:
                    return True
    else:
        raise NotImplemented("not support {0}".format(match_result.logicOperator))


def __check_condition(condition_holder: Conditional, pipeline_topic, data, context):
    if condition_holder.conditional and condition_holder.on is not None:
        condition: ParameterJoint = condition_holder.on
        return __check_on_condition(
            __build_on_condition(condition, pipeline_topic, data[pipeline_constants.NEW], context))
    else:
        return True


def __build_mongo_update(update_data, arithmetic, target_factor, old_value_list=None):
    # print("arithmetic",arithmetic)
    # print(update_data)
    if arithmetic == "sum":
        if old_value_list is not None:
            dif_update_value = {target_factor.name: update_data[target_factor.name] - old_value_list}
            return {"$inc": dif_update_value}
        else:
            return {"$inc": update_data}
    elif arithmetic == "count":
        if old_value_list is not None:
            return {"$inc": {target_factor.name: 0}}
        else:
            return {"$inc": {target_factor.name: 1}}
    ## TODO re-factor max and min

    elif arithmetic == "max":
        return {"$max": update_data}
    elif arithmetic == "min":
        return {"$min": update_data}
    else:
        return {"$set": update_data}


def __process_where_condition(where_condition):
    if where_condition[pipeline_constants.OPERATOR] == parameter_constants.EQUALS:
        return {where_condition[pipeline_constants.NAME].name: where_condition[pipeline_constants.VALUE]}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.EMPTY:
        # return {where_condition[pipeline_constants.NAME].name: {"$eq": None}}
        return {where_condition[pipeline_constants.NAME].name: {"=": None}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.NOT_EMPTY:
        # return {where_condition[pipeline_constants.NAME].name: {"$ne": None}}
        return {where_condition[pipeline_constants.NAME].name: {"!=": None}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.NOT_EQUALS:
        # return {where_condition[pipeline_constants.NAME].name: {"$ne": where_condition[pipeline_constants.VALUE]}}
        return {where_condition[pipeline_constants.NAME].name: {"!=": where_condition[pipeline_constants.VALUE]}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.MORE:
        # return {where_condition[pipeline_constants.NAME].name: {"$gt": where_condition[pipeline_constants.VALUE]}}
        return {where_condition[pipeline_constants.NAME].name: {">": where_condition[pipeline_constants.VALUE]}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.LESS:
        # return {where_condition[pipeline_constants.NAME].name: {"$lt": where_condition[pipeline_constants.VALUE]}}
        return {where_condition[pipeline_constants.NAME].name: {"<": where_condition[pipeline_constants.VALUE]}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.MORE_EQUALS:
        # return {where_condition[pipeline_constants.NAME].name: {"$gte": where_condition[pipeline_constants.VALUE]}}
        return {where_condition[pipeline_constants.NAME].name: {">=": where_condition[pipeline_constants.VALUE]}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.LESS_EQUALS:
        # return {where_condition[pipeline_constants.NAME].name: {"$lte": where_condition[pipeline_constants.VALUE]}}
        return {where_condition[pipeline_constants.NAME].name: {"<=": where_condition[pipeline_constants.VALUE]}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.IN:
        '''
        return {where_condition[pipeline_constants.NAME].name: {
            "$in": __convert_to_list(where_condition[pipeline_constants.VALUE])}}
        '''
        return {where_condition[pipeline_constants.NAME].name: {
            "in": __convert_to_list(where_condition[pipeline_constants.VALUE])}}
    elif where_condition[pipeline_constants.OPERATOR] == parameter_constants.NOT_IN:
        '''
        return {where_condition[pipeline_constants.NAME].name: {
            "$nin": __convert_to_list(where_condition[pipeline_constants.VALUE])}}
        '''
        return {where_condition[pipeline_constants.NAME].name: {
            "not in": __convert_to_list(where_condition[pipeline_constants.VALUE])}}


# def __build_index_condition_result(result,condition_values,where_condition,index):
#     if type(condition_values[VALUE]) == list:
#         result[VALUE] = where_condition[index]
#         return result
#     else:
#         return result

def index_conditions(where_condition, index):
    result = where_condition.copy()
    if type(where_condition) == list:
        for index, condition in enumerate(where_condition):
            condition_values = condition[pipeline_constants.VALUE]
            if type(condition_values) == list:
                result[index][VALUE] = condition[pipeline_constants.VALUE]
            return result
    else:
        # print("where_condition",where_condition)
        condition_values = where_condition[pipeline_constants.VALUE]
        if type(condition_values) == list:
            result[VALUE] = condition_values[index]
            return result
        else:
            return result

    result = where_condition.copy()
    # print("where_condition",where_condition)
    condition_values = where_condition[index]
    if type(condition_values[VALUE]) == list:
        result[VALUE] = where_condition[index]
        return result
    else:
        return result


def __build_mongo_query(joint_type, where_condition):
    if joint_type is None:
        return __process_where_condition(where_condition)
    else:
        where_condition_result = {}
        if joint_type == parameter_constants.AND:
            # where_condition_result[mongo_constants.MONGO_AND] = []
            where_condition_result["and"] = []
            for condition in where_condition:
                # where_condition_result[mongo_constants.MONGO_AND].append(__process_where_condition(condition))
                where_condition_result["and"].append(__process_where_condition(condition))
        elif joint_type == parameter_constants.OR:
            # where_condition_result[mongo_constants.MONGO_OR] = []
            where_condition_result["or"] = []
            for condition in where_condition:
                where_condition_result["or"].append(__process_where_condition(condition))
        return where_condition_result
