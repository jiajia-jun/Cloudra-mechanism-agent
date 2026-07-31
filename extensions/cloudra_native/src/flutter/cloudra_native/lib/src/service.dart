import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class CloudraNativeService extends FletService {
  static const MethodChannel _channel =
      MethodChannel('io.github.yyywaa.cloudra/native');

  CloudraNativeService({required super.control});

  @override
  void init() {
    super.init();
    debugPrint('CloudraNativeService(${control.id}).init');
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    final arguments =
        args is Map ? Map<String, dynamic>.from(args) : <String, dynamic>{};
    return _channel.invokeMethod<dynamic>(name, arguments);
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
