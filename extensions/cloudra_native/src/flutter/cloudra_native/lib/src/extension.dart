import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';

import 'service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    if (control.type == 'CloudraNative') {
      return CloudraNativeService(control: control);
    }
    return null;
  }

  @override
  Widget? createWidget(Key? key, Control control) => null;
}
