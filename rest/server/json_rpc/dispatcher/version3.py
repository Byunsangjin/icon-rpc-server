# Copyright 2017 theloop Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""json rpc dispatcher version 3"""

import json
import logging

from earlgrey import MessageQueueException
from jsonrpcserver import config, status
from jsonrpcserver.aio import AsyncMethods
from sanic import response as sanic_response

import rest.configure.configure as conf
from ....protos import message_code
from ...rest_server import RestProperty
from ...json_rpc import exception
from ....utils.icon_service import make_request, response_to_json_query, ParamType, convert_params
from ....utils.json_rpc import redirect_request_to_rs, get_block_by_params
from ....utils.message_queue import StubCollection
from rest.server.json_rpc.validator import validate_jsonschema_v3

config.log_requests = False
config.log_responses = False

methods = AsyncMethods()


class Version3Dispatcher:
    @staticmethod
    async def dispatch(request):
        req = request.json

        validate_jsonschema_v3(request=req)

        dispatch_response = await methods.dispatch(req)
        return sanic_response.json(dispatch_response, status=dispatch_response.http_status, dumps=json.dumps)

    @staticmethod
    @methods.add
    async def icx_call(**kwargs):
        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL
        score_stub = StubCollection().icon_score_stubs[channel_name]

        method = 'icx_call'
        request = make_request(method, kwargs)
        response = await score_stub.async_task().query(request)

        response_to_json_query(response)
        return response

    @staticmethod
    @methods.add
    async def icx_getScoreApi(**kwargs):
        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL
        score_stub = StubCollection().icon_score_stubs[channel_name]

        method = 'icx_getScoreApi'
        request = make_request(method, kwargs)
        response = await score_stub.async_task().query(request)

        response_to_json_query(response)
        return response

    @staticmethod
    @methods.add
    async def icx_sendTransaction(**kwargs):
        if RestProperty().node_type == conf.NodeType.CitizenNode:
            return await redirect_request_to_rs(kwargs, RestProperty().rs_target)

        by_citizen = kwargs.get("node_type", False)
        if by_citizen:
            kwargs = kwargs["message"]

        method = 'icx_sendTransaction'
        request = make_request(method, kwargs)
        icon_stub = StubCollection().icon_score_stubs[conf.LOOPCHAIN_DEFAULT_CHANNEL]
        response = await icon_stub.async_task().validate_transaction(request)
        response_to_json_query(response)

        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL
        channel_stub = StubCollection().channel_stubs[channel_name]
        tx_hash = await channel_stub.async_task().create_icx_tx(kwargs)

        return convert_params(tx_hash, ParamType.send_tx_response)

    @staticmethod
    @methods.add
    async def icx_getTransactionResult(**kwargs):
        if RestProperty().node_type == conf.NodeType.CitizenNode:
            return await redirect_request_to_rs(kwargs, RestProperty().rs_target)

        by_citizen = kwargs.get("node_type", False)
        if by_citizen:
            kwargs = kwargs["message"]

        request = convert_params(kwargs, ParamType.get_tx_request)

        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL
        channel_stub = StubCollection().channel_stubs[channel_name]
        verify_result = dict()

        tx_hash = request["txHash"]
        response_code, result = await channel_stub.async_task().get_invoke_result(tx_hash)

        if response_code == message_code.Response.fail_invalid_key_error or \
            response_code == message_code.Response.fail:
            raise exception.GenericJsonRpcServerError(
                code=exception.INVALID_PARAMS,
                message='Invalid params txHash',
                http_status=status.HTTP_BAD_REQUEST
            )

        if result:
            try:
                result_dict = json.loads(result)
                verify_result = result_dict
            except json.JSONDecodeError as e:
                logging.warning(f"your result is not json, result({result}), {e}")

        response = convert_params(verify_result, ParamType.get_tx_result_response)
        return response

    @staticmethod
    @methods.add
    async def icx_getTransactionByHash(**kwargs):
        request = convert_params(kwargs, ParamType.get_tx_request)

        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL
        channel_stub = StubCollection().channel_stubs[channel_name]

        tx_info = await channel_stub.async_task().get_tx_info(request["txHash"])
        if tx_info == message_code.Response.fail_invalid_key_error:
            raise exception.GenericJsonRpcServerError(
                code=exception.INVALID_PARAMS,
                message='Invalid params txHash',
                http_status=status.HTTP_BAD_REQUEST
            )

        result = tx_info["transaction"]
        result["txIndex"] = tx_info["tx_index"]
        result["blockHeight"] = tx_info["block_height"]
        result["blockHash"] = tx_info["block_hash"]

        response = convert_params(result, ParamType.get_tx_by_hash_response)
        return response

    @staticmethod
    @methods.add
    async def icx_getBalance(**kwargs):
        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL
        score_stub = StubCollection().icon_score_stubs[channel_name]

        method = 'icx_getBalance'
        request = make_request(method, kwargs)
        response = await score_stub.async_task().query(request)

        response_to_json_query(response)
        return response

    @staticmethod
    @methods.add
    async def icx_getTotalSupply(**kwargs):
        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL
        score_stub = StubCollection().icon_score_stubs[channel_name]

        method = 'icx_getTotalSupply'
        request = make_request(method, kwargs)
        response = await score_stub.async_task().query(request)

        response_to_json_query(response)
        return response

    @staticmethod
    @methods.add
    async def icx_getLastBlock(**kwargs):
        block_hash, result = await get_block_by_params(block_height=-1)
        response = convert_params(result['block'], ParamType.get_block_response)

        return response

    @staticmethod
    @methods.add
    async def icx_getBlockByHash(**kwargs):
        request = convert_params(kwargs, ParamType.get_block_by_hash_request)

        block_hash, result = await get_block_by_params(block_hash=request['hash'])
        if result['response_code'] == message_code.Response.fail_wrong_block_hash:
            raise exception.GenericJsonRpcServerError(
                code=exception.INVALID_PARAMS,
                message='Invalid params hash',
                http_status=status.HTTP_BAD_REQUEST
            )

        response = convert_params(result['block'], ParamType.get_block_response)

        return response

    @staticmethod
    @methods.add
    async def icx_getBlockByHeight(**kwargs):
        request = convert_params(kwargs, ParamType.get_block_by_height_request)

        try:
            block_hash, result = await get_block_by_params(block_height=request['height'])
        except MessageQueueException as e:
            raise exception.GenericJsonRpcServerError(
                code=exception.INVALID_PARAMS,
                message='Invalid params height',
                http_status=status.HTTP_BAD_REQUEST
            )
        
        response = convert_params(result['block'], ParamType.get_block_response)

        return response

    @staticmethod
    @methods.add
    async def icx_getLastTransaction(**kwargs):
        channel_name = conf.LOOPCHAIN_DEFAULT_CHANNEL

        return ""
