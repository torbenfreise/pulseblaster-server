import functools
import logging

import grpc
from h2pcontrol.pulseblaster.v1.pulseblaster_pb2 import (
    BoardInfo,
    BoardStatus,
    GetBoardInfoRequest,
    GetBoardInfoResponse,
    GetStatusRequest,
    GetStatusResponse,
    ProgramRequest,
    ProgramResponse,
    ResetRequest,
    ResetResponse,
    StartRequest,
    StartResponse,
    StopRequest,
    StopResponse,
)
from h2pcontrol.pulseblaster.v1.pulseblaster_pb2_grpc import PulseBlasterServiceServicer
from h2pcontrol.sdk.server import Server, ServerConfig

from spincore import spinapi
from spincore.pulseblaster import PulseBlaster, PulseBlasterError

logger = logging.getLogger(__name__)


def handle_pb_errors(method):
    @functools.wraps(method)
    async def wrapper(self, request, context):
        try:
            return await method(self, request, context)
        except PulseBlasterError as e:
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    return wrapper


class PulseBlasterService(Server, PulseBlasterServiceServicer):
    def __init__(self, config: ServerConfig):
        super().__init__(config)
        self.pb = PulseBlaster()

    def _healthy(self) -> bool:
        return True

    @handle_pb_errors
    async def GetBoardInfo(self, request: GetBoardInfoRequest, context):
        return GetBoardInfoResponse(
            board_info=BoardInfo(
                firmware_id=spinapi.pb_get_firmware_id(),
                clock_frequency_mhz=self.pb.clock,
                num_channels=self.pb.channels,
            )
        )

    _STATUS_MAP = {
        spinapi.STATUS_STOPPED: BoardStatus.BOARD_STATUS_STOPPED,
        spinapi.STATUS_RESET: BoardStatus.BOARD_STATUS_RESET,
        spinapi.STATUS_RUNNING: BoardStatus.BOARD_STATUS_RUNNING,
        spinapi.STATUS_WAITING: BoardStatus.BOARD_STATUS_WAITING,
    }

    @handle_pb_errors
    async def GetStatus(self, request: GetStatusRequest, context):
        s = spinapi.pb_read_status()
        status = BoardStatus.BOARD_STATUS_UNSPECIFIED
        for bit, proto_status in self._STATUS_MAP.items():
            if s & bit:
                status = proto_status
        return GetStatusResponse(status=status)

    @handle_pb_errors
    async def Program(self, request: ProgramRequest, context):
        match request.WhichOneof("program"):
            case "instructions":
                for instruction in request.instructions.instructions:
                    self.pb.add_inst(
                        flags=instruction.flags,
                        inst=instruction.op_code,
                        inst_data=instruction.inst_data,
                        length=instruction.duration_ns,
                    )
            case "channels":
                for sequence in request.channels.sequences:
                    self.pb.set_channel(
                        sequence.channel,
                        [(pulse.high, pulse.duration_ns) for pulse in sequence.pulses],
                    )
                self.pb.compile_channels()
        self.pb.program()
        return ProgramResponse()

    @handle_pb_errors
    async def Start(self, request: StartRequest, context):
        self.pb.start()
        return StartResponse()

    @handle_pb_errors
    async def Stop(self, request: StopRequest, context):
        self.pb.stop()
        return StopResponse()

    @handle_pb_errors
    async def Reset(self, request: ResetRequest, context):
        self.pb.reset()
        return ResetResponse()
