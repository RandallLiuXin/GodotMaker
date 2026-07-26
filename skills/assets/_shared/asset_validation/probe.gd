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
const KNOWN_CHECKS := ["texture2d", "atlas_texture", "spriteframes", "stylebox_texture"]


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
			"atlas_texture":
				if resource.is_class("AtlasTexture"):
					var atlas_texture: AtlasTexture = resource
					var atlas_path := ""
					if atlas_texture.atlas != null:
						atlas_path = atlas_texture.atlas.resource_path
					var region := atlas_texture.region
					var margin := atlas_texture.margin
					structure[check] = {
						"has_atlas": atlas_texture.atlas != null,
						"atlas_path": atlas_path,
						"region": [region.position.x, region.position.y, region.size.x, region.size.y],
						"margin": [margin.position.x, margin.position.y, margin.size.x, margin.size.y],
					}
				else:
					structure[check] = {
						"error": "resource is a %s, not an AtlasTexture" % resource.get_class(),
					}
			"spriteframes":
				if resource.is_class("SpriteFrames"):
					var animations := []
					for animation_name in resource.get_animation_names():
						var frame_paths := []
						var frame_durations := []
						var frame_count := resource.get_frame_count(animation_name)
						for frame_index in range(frame_count):
							var texture := resource.get_frame_texture(animation_name, frame_index)
							frame_paths.append(texture.resource_path if texture != null else "")
							frame_durations.append(resource.get_frame_duration(animation_name, frame_index))
						animations.append({
							"name": str(animation_name),
							"fps": resource.get_animation_speed(animation_name),
							"loop": resource.get_animation_loop(animation_name),
							"frame_count": frame_count,
							"frame_paths": frame_paths,
							"frame_durations": frame_durations,
						})
					structure[check] = {"animations": animations}
				else:
					structure[check] = {"error": "resource is a %s, not SpriteFrames" % resource.get_class()}
			"stylebox_texture":
				if resource.is_class("StyleBoxTexture"):
					var style_box: StyleBoxTexture = resource
					var texture_path := ""
					if style_box.texture != null:
						texture_path = style_box.texture.resource_path
					var region := style_box.region_rect
					structure[check] = {
						"has_texture": style_box.texture != null,
						"texture_path": texture_path,
						"texture_region": [region.position.x, region.position.y, region.size.x, region.size.y],
						"border": [style_box.texture_margin_left, style_box.texture_margin_top, style_box.texture_margin_right, style_box.texture_margin_bottom],
						"expand_margin": [style_box.expand_margin_left, style_box.expand_margin_top, style_box.expand_margin_right, style_box.expand_margin_bottom],
						"axis_stretch": [style_box.axis_stretch_horizontal, style_box.axis_stretch_vertical],
					}
				else:
					structure[check] = {"error": "resource is a %s, not StyleBoxTexture" % resource.get_class()}
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
