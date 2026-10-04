# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panels (3D Viewport › N › Animation Sculptor)."""

import bpy

CATEGORY = "Animation Sculptor"
TOOL_ID = "animation_sculptor.sculpt"   # interaction.sculpt_tool.TOOL_ID (no import: ui must load first)


def _tool_active(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except Exception:
        return False
    return tool is not None and tool.idname == TOOL_ID


class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY


class ASC_PT_main(_Base, bpy.types.Panel):
    bl_idname = "ASC_PT_main"
    bl_label = "Animation Sculptor"

    def draw(self, context):
        layout = self.layout
        ob = context.active_object
        col = layout.column(align=True)
        if ob is None or ob.type != 'ARMATURE':
            col.label(text="Selecione uma armature", icon='INFO')
        elif ob.mode != 'POSE':
            col.label(text="Entre em Pose Mode", icon='INFO')
        else:
            from .. import rig

            adapter = rig.get_adapter(ob)
            col.label(text=f"Rig: {ob.name} ({adapter.id})", icon='ARMATURE_DATA')
            pb = context.active_pose_bone
            if pb is not None:
                info = adapter.classify(ob, pb.name)
                if info is None:
                    col.label(text=f"{pb.name}: não é controle", icon='LOCKED')
                else:
                    caps = " + ".join(sorted(c.lower() for c in info.capabilities)) or "travado"
                    concept = f" · {info.concept}" if info.concept else ""
                    col.label(text=f"{pb.name}{concept}: {caps}", icon='BONE_DATA')
        row = layout.row(align=True)
        row.scale_y = 1.2
        if ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE':
            active = _tool_active(context)
            op = row.operator("wm.tool_set_by_id", text="Ferramenta ativa" if active else "Ativar ferramenta",
                              icon='CHECKMARK' if active else 'TOOL_SETTINGS', depress=active)
            op.name = TOOL_ID
        trails = getattr(context.scene, "asc_trails", None)
        if trails is not None:
            row.prop(trails, "enabled", text="Trails", toggle=True,
                     icon='IPO_BEZIER' if trails.enabled else 'CURVE_PATH')


class ASC_PT_tool(_Base, bpy.types.Panel):
    bl_idname = "ASC_PT_tool"
    bl_label = "Gestos"
    bl_parent_id = "ASC_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        settings = getattr(context.scene, "asc_sculpt", None)
        if settings is None:
            return
        col = layout.column(align=True)
        col.label(text="Espaço (arrastar)", icon='OBJECT_ORIGIN')
        col.prop(settings, "soft_radius", text="Raio (frames)")
        col.prop(settings, "falloff")
        col = layout.column(align=True)
        col.label(text="Tempo (Ctrl+arrastar)", icon='TIME')
        col.prop(settings, "timing_scope", text="Escopo")
        col.prop(settings, "spacing_policy")
        trails = getattr(context.scene, "asc_trails", None)
        if trails is not None:
            col.prop(trails, "path_color_mode", text="Cor da trail")
        layout.prop(settings, "hide_on_playback")
        box = layout.box()
        box.scale_y = 0.8
        for line in ("Arrastar losango: grab · roda/[ ]: raio",
                     "Arrastar ponto: arco · B: quebrar tangente",
                     "Ctrl+losango: retime · Ctrl+ponto: spacing",
                     "Shift: precisão · Esc/RMB: cancelar",
                     "Shift+Alt+K: ativar a ferramenta"):
            box.label(text=line)


class ASC_PT_breakdown(_Base, bpy.types.Panel):
    bl_idname = "ASC_PT_breakdown"
    bl_label = "Breakdown"
    bl_parent_id = "ASC_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Operadores nativos do Blender (bones selecionados):")
        col = layout.column(align=True)
        col.operator("pose.breakdown", text="Breakdowner", icon='IPO_EASE_IN_OUT')
        row = col.row(align=True)
        row.operator("pose.push", text="Push")
        row.operator("pose.relax", text="Relax")
        col.operator("pose.blend_to_neighbor", text="Blend to Neighbor")
        layout.label(text="Arraste o mouse para favorecer a pose anterior/seguinte.", icon='INFO')


class ASC_PT_stats(_Base, bpy.types.Panel):
    bl_idname = "ASC_PT_stats"
    bl_label = "Estatísticas"
    bl_parent_id = "ASC_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        from ..interaction import state
        from ..trails import provider

        col = self.layout.column(align=True)
        stats = state.STATS
        labels = (("last_move_ms", "Último mouse move", "ms"), ("prefetch_ms", "Pré-cálculo de P(f)", "ms"),
                  ("prefetch_frames", "Frames pré-calculados", ""), ("refresh_ms", "Refresh ao soltar", "ms"))
        for key, label, unit in labels:
            if key in stats:
                col.label(text=f"{label}: {stats[key]:.2f} {unit}".rstrip())
        trail_stats = provider.stats()
        col.label(text=f"Trails: {trail_stats['targets']} alvo(s), {trail_stats['last_compute_ms']:.0f} ms "
                       f"({trail_stats['engines'] or '-'})")


classes = (ASC_PT_main, ASC_PT_tool, ASC_PT_breakdown, ASC_PT_stats)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
