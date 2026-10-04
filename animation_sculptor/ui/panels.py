# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panels (3D Viewport › N › Animation Sculptor)."""

import bpy

CATEGORY = "Animation Sculptor"
TOOL_ID = "animation_sculptor.sculpt"   # interaction.sculpt_tool ids (no import: ui must load first)
TOOL_IDS = ("animation_sculptor.tip", TOOL_ID, "animation_sculptor.body", "animation_sculptor.smooth")


def _tool_active(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except Exception:
        return False
    return tool is not None and tool.idname in TOOL_IDS


class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY


class ASC_PT_main(_Base, bpy.types.Panel):
    """Clean on purpose (decision of 2026-10-04): the tools live in the toolbar; here only the mode and the
    simple toggles. Parameters and debugging are in the closed sub-panels."""
    bl_idname = "ASC_PT_main"
    bl_label = "Animation Sculptor"

    def draw(self, context):
        layout = self.layout
        ob = context.active_object
        settings = getattr(context.scene, "asc_sculpt", None)
        if ob is None or ob.type != 'ARMATURE':
            layout.label(text="Selecione uma armature", icon='INFO')
        elif ob.mode != 'POSE':
            layout.label(text="Entre em Pose Mode", icon='INFO')
        elif not _tool_active(context):
            op = layout.operator("wm.tool_set_by_id", text="Ativar ferramenta (Shift+Alt+K)", icon='TOOL_SETTINGS')
            op.name = TOOL_ID
        if settings is None:
            return
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.prop(settings, "interaction_mode", expand=True)
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(settings, "show_trails", text="Trails", toggle=True, icon='IPO_BEZIER')
        row.prop(settings, "show_rig", text="Ligar Rigify", toggle=True, icon='ARMATURE_DATA')
        row = col.row(align=True)
        row.prop(settings, "onion_show", text="Onion skin", toggle=True, icon='ONIONSKIN_ON')
        sub = row.row(align=True)
        sub.active = settings.onion_show
        sub.prop(settings, "onion_spread", text="Onion expandida", toggle=True, icon='ARROW_LEFTRIGHT')


class ASC_PT_tool(_Base, bpy.types.Panel):
    bl_idname = "ASC_PT_tool"
    bl_label = "Parâmetros"
    bl_parent_id = "ASC_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        settings = getattr(context.scene, "asc_sculpt", None)
        if settings is None:
            return
        col = layout.column(align=True)
        col.label(text="Janela de tempo (régua)", icon='TIME')
        row = col.row(align=True)
        row.prop(settings, "radius_past", text="Raio passado")
        row.prop(settings, "radius_linked", text="", icon='LINKED' if settings.radius_linked else 'UNLINKED')
        col.prop(settings, "radius_future", text="Raio futuro")
        col.prop(settings, "falloff")
        col.prop(settings, "show_time_ruler")
        col = layout.column(align=True)
        col.label(text="Corpo / Membro / Ponta", icon='BONE_DATA')
        col.prop(settings, "tip_orientation", text="Mão/pé")
        col.prop(settings, "smooth_strength")
        col.prop(settings, "smooth_sigma")
        col = layout.column(align=True)
        col.label(text="Trail: tempo (Ctrl+arrastar)", icon='IPO_EASE_IN_OUT')
        col.prop(settings, "timing_scope", text="Escopo")
        col.prop(settings, "spacing_policy")
        trails = getattr(context.scene, "asc_trails", None)
        if trails is not None:
            row = col.row(align=True)
            row.prop(trails, "path_color_mode", text="Cor da trail")
            row.operator("asc.apply_palette", text="", icon='COLOR')
        layout.prop(settings, "hide_on_playback")
        box = layout.box()
        box.scale_y = 0.8
        for line in ("Corpo: arraste o corpo do personagem (pose/arco no frame atual)",
                     "Ferramentas na barra lateral: Ponta · Membro · Corpo · Smooth",
                     "Trail: losango = grab · ponto = arco · Ctrl = retime/spacing",
                     "Pontas da régua: raio passado/futuro (Shift: os dois) · roda/[ ]: raio",
                     "Shift: precisão · Esc/RMB: cancelar · Shift+Alt+K: ferramenta"):
            box.label(text=line)


class ASC_OT_apply_palette(bpy.types.Operator):
    """Reaplica a paleta do Animation Sculptor às trails e ao onion skin: passado vermelho, futuro verde"""
    bl_idname = "asc.apply_palette"
    bl_label = "Paleta Animation Sculptor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..trails import provider

        if not provider.apply_palette(context.scene):
            return {'CANCELLED'}
        settings = getattr(context.scene, "asc_sculpt", None)
        if settings is not None:
            settings.palette_applied = True
        return {'FINISHED'}


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


classes = (ASC_OT_apply_palette, ASC_PT_main, ASC_PT_tool, ASC_PT_breakdown, ASC_PT_stats)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
