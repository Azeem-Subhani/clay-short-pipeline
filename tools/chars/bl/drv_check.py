import bpy
bad = [(o.name, fc.data_path) for o in bpy.data.objects if o.animation_data for fc in o.animation_data.drivers if not fc.driver.is_valid or (fc.driver.type == "SCRIPTED" and not fc.driver.is_simple_expression)]
print("DRIVERS_NOT_SIMPLE", len(bad), bad[:5])
