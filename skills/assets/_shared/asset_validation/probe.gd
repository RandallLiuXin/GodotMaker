# L3 of the asset readiness ladder, running inside headless Godot.
#
# Reads a request JSON, loads each resource through ResourceLoader, and writes a
# report JSON. It reports facts and never decides readiness: the Python side
# owns the verdict, so a probe that cannot answer produces an error string
# rather than an optimistic default.
#
# The report goes to a file rather than stdout because Godot writes engine
# banners, import notices, and resource errors to the same streams, and a
# resource that fails to load is exactly the case that floods them.
#
# Invoked as:
#   godot --headless --path <project> --script <this file> --
#         --request <abs path> --report <abs path>
extends SceneTree

# Structural facts a resource may be asked to report for L4. The set is closed:
# an unknown check is an error, never a silent pass. A family skill adds its
# check name here together with the Python structure validator that consumes it.
const KNOWN_CHECKS := ["texture2d", "theme"]


func _parse_user_args() -> Dictionary:
	var options := {}
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		var argument: String = args[index]
		if argument.begins_with("--") and index + 1 < args.size():
			options[argument.substr(2)] = args[index + 1]
			index += 2
		else:
			index += 1
	return options


func _structure(resource: Resource, checks: Array) -> Dictionary:
	var structure := {}
	for check in checks:
		if not (check in KNOWN_CHECKS):
			structure[check] = {"error": "unknown structural check: %s" % check}
			continue
		match check:
			"texture2d":
				if resource.is_class("Texture2D"):
					structure[check] = {
						"width": resource.get_width(),
						"height": resource.get_height(),
					}
				else:
					structure[check] = {
						"error": "resource is a %s, not a Texture2D" % resource.get_class(),
					}
			"theme":
				if resource.is_class("Theme"):
					var types := {}
					for theme_type in resource.get_type_list():
						var type_name := str(theme_type)
						var styleboxes := {}
						for style_name in resource.get_stylebox_list(theme_type):
							var stylebox := resource.get_stylebox(style_name, theme_type)
							var stylebox_facts := {"class": stylebox.get_class()}
							if stylebox.is_class("StyleBoxFlat"):
								var flat := stylebox as StyleBoxFlat
								stylebox_facts["border_width"] = {
									"left": flat.border_width_left,
									"top": flat.border_width_top,
									"right": flat.border_width_right,
									"bottom": flat.border_width_bottom,
								}
							styleboxes[str(style_name)] = stylebox_facts
						types[type_name] = {
							"variation_base": str(resource.get_type_variation_base(theme_type)),
							"colors": resource.get_color_list(theme_type),
							"font_sizes": resource.get_font_size_list(theme_type),
							"constants": resource.get_constant_list(theme_type),
							"fonts": resource.get_font_list(theme_type),
							"icons": resource.get_icon_list(theme_type),
							"styles": resource.get_stylebox_list(theme_type),
							"styleboxes": styleboxes,
						}
					structure[check] = {"types": types}
				else:
					structure[check] = {
						"error": "resource is a %s, not a Theme" % resource.get_class(),
					}
	return structure


func _probe(item: Dictionary) -> Dictionary:
	var path: String = item.get("path", "")
	var expected_type: String = item.get("expected_type", "")
	var report := {
		"path": path,
		"expected_type": expected_type,
		"loaded": false,
		"class": "",
		"type_matches": false,
		"structure": {},
		"error": null,
	}
	if path == "" or expected_type == "":
		report["error"] = "request item needs both a path and an expected_type"
		return report
	if not ResourceLoader.exists(path):
		report["error"] = "Godot has no importable resource at %s" % path
		return report
	# CACHE_MODE_IGNORE forces a real load: a cached instance from an earlier
	# probe in the same run would prove nothing about the file on disk.
	var resource := ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if resource == null:
		report["error"] = "ResourceLoader.load returned null for %s" % path
		return report
	report["loaded"] = true
	report["class"] = resource.get_class()
	# is_class covers the whole inheritance chain, so an imported PNG reporting
	# CompressedTexture2D still matches a declared Texture2D.
	report["type_matches"] = resource.is_class(expected_type)
	report["structure"] = _structure(resource, item.get("checks", []))
	return report


func _fail(message: String, code: int) -> void:
	printerr("asset validation probe: %s" % message)
	quit(code)


func _initialize() -> void:
	var options := _parse_user_args()
	var request_path: String = options.get("request", "")
	var report_path: String = options.get("report", "")
	if request_path == "" or report_path == "":
		_fail("both --request and --report are required", 2)
		return

	var request_file := FileAccess.open(request_path, FileAccess.READ)
	if request_file == null:
		_fail("cannot read request file %s" % request_path, 2)
		return
	var request = JSON.parse_string(request_file.get_as_text())
	request_file.close()
	if typeof(request) != TYPE_DICTIONARY:
		_fail("request file %s is not a JSON object" % request_path, 2)
		return

	var reports := []
	for item in request.get("resources", []):
		if typeof(item) != TYPE_DICTIONARY:
			_fail("every request resource must be a JSON object", 2)
			return
		reports.append(_probe(item))

	var report_file := FileAccess.open(report_path, FileAccess.WRITE)
	if report_file == null:
		_fail("cannot write report file %s" % report_path, 3)
		return
	report_file.store_string(JSON.stringify({
		"godot_version": Engine.get_version_info().get("string", ""),
		"resources": reports,
	}))
	report_file.close()
	quit(0)
