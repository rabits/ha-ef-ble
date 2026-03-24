# -*- coding: utf-8 -*-
# Generated-like protobuf definitions for ac517_powerpulse_ev.proto.

from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

_sym_db = _symbol_database.Default()


_file = _descriptor_pb2.FileDescriptorProto()
_file.name = "ac517_powerpulse_ev.proto"
_file.package = "ac517_powerpulse_ev"
_file.syntax = "proto3"

_metrics = _file.message_type.add()
_metrics.name = "Cmd2_2_33Metrics"

_field = _metrics.field.add()
_field.name = "power_w"
_field.number = 4
_field.label = _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
_field.type = _descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT

_field = _metrics.field.add()
_field.name = "voltage_v"
_field.number = 7
_field.label = _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
_field.type = _descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT

_field = _metrics.field.add()
_field.name = "current_a"
_field.number = 10
_field.label = _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
_field.type = _descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT

_status = _file.message_type.add()
_status.name = "Cmd2_2_33Status"

_field = _status.field.add()
_field.name = "state"
_field.number = 1
_field.label = _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
_field.type = _descriptor_pb2.FieldDescriptorProto.TYPE_UINT32

_field = _status.field.add()
_field.name = "metrics"
_field.number = 8
_field.label = _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
_field.type = _descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
_field.type_name = ".ac517_powerpulse_ev.Cmd2_2_33Metrics"

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(_file.SerializeToString())

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(
    DESCRIPTOR, "ac517_powerpulse_ev_pb2", globals()
)
