import bpy, re
from bpy.props import *
from ... utils.nodes import getNode
from ... base_types.node import AnimationNode
from ... utils.nodes import NodeTreeInfo
from ... utils.names import getPossibleSocketName, toInterfaceName
from ... sockets.info import getDataTypeItems, toIdName

emptySocketName = "New Socket"

class ScriptNode(bpy.types.Node, AnimationNode):
    bl_idname = "an_ScriptNode"
    bl_label = "Script"

    def makeFromClipboardChanged(self, context):
        if self.makeFromClipboard:
            self.buildFromText(context.window_manager.clipboard)

    def hideEditableElementsChanged(self, context):
        hide = self.hideEditableElements
        for socket in list(self.inputs) + list(self.outputs):
            if socket.name == emptySocketName:
                socket.hide = hide
            else:
                socket.nameSettings.editable = not hide
                socket.removeable = not hide
                self.customSocketNameChanged(socket)

    def enableUINameConversionChanged(self, context):
        for socket in list(self.inputs) + list(self.outputs):
            self.customSocketNameChanged(socket)

    textBlockName = StringProperty(name = "Script", default = "", description = "Choose the script you want to execute in this node")
    errorMessage = StringProperty(name = "Error Message", default = "")
    selectedSocketType = EnumProperty(name = "Selected Socket Type", items = getDataTypeItems)
    makeFromClipboard = BoolProperty(default = False, update = makeFromClipboardChanged)
    hideEditableElements = BoolProperty(name = "Hide Editable Elements", default = False, update = hideEditableElementsChanged)
    enableUINameConversion = BoolProperty(name = "Auto Socket Names", default = True, update = enableUINameConversionChanged)
    showErrorMessage = BoolProperty(name = "Show Error Message", default = True)

    def create(self):
        self.createEmptySockets()

    def draw(self, layout):
        if not self.hideEditableElements:
            row = layout.row(align = True)
            row.prop_search(self, "textBlockName",  bpy.data, "texts", text = "")
            operator = row.operator("an.open_new_script", text = "", icon = "PLUS")
            operator.nodeTreeName = self.id_data.name
            operator.nodeName = self.name

        if self.showErrorMessage and self.errorMessage != "":
            layout.label(self.errorMessage, icon = "ERROR")

        if not self.hideEditableElements:
            layout.separator()

    def drawAdvanced(self, layout):
        col = layout.column(align = True)
        col.label("New Socket")
        col.prop(self, "selectedSocketType", text = "")

        row = col.row(align = True)

        operator = row.operator("an.append_socket_to_script_node", text = "Input")
        operator.nodeTreeName = self.id_data.name
        operator.nodeName = self.name
        operator.makeOutputSocket = False

        operator = row.operator("an.append_socket_to_script_node", text = "Output")
        operator.nodeTreeName = self.id_data.name
        operator.nodeName = self.name
        operator.makeOutputSocket = True

        operator = layout.operator("an.export_script_node")
        operator.nodeTreeName = self.id_data.name
        operator.nodeName = self.name

        col = layout.column(align = True)
        col.prop(self, "hideEditableElements")
        col.prop(self, "enableUINameConversion")
        col.prop(self, "showErrorMessage")

    def edit(self):
        nodeTreeInfo = NodeTreeInfo(self.id_data)
        for sockets in (self.inputs, self.outputs):
            emptySocket = sockets.get(emptySocketName)
            if emptySocket:
                linkedDataSocket = nodeTreeInfo.getFirstLinkedSocket(emptySocket)
                if linkedDataSocket:
                    link = emptySocket.links[0]
                    type = linkedDataSocket.bl_idname
                    if type != "an_EmptySocket":
                        newSocket = self.appendSocket(sockets, linkedDataSocket.bl_idname, linkedDataSocket.name)
                        linkedSocket = self.getSocketFromOtherNode(link)
                        self.id_data.links.remove(link)
                        self.makeLink(newSocket, linkedSocket)

    def createEmptySockets(self):
        for sockets in (self.inputs, self.outputs):
            socket = sockets.new("an_EmptySocket", emptySocketName)
            socket.passiveType = "an_GenericSocket"
            socket.customName = "EMPTYSOCKET"

    def appendSocket(self, sockets, type, name):
        socket = sockets.new(type, name)
        self.setupNewSocket(socket, name)
        sockets.move(len(sockets)-1, len(sockets)-2)
        return socket

    def setupNewSocket(self, socket, name):
        socket.nameSettings.editable = True
        socket.nameSettings.variable = True
        socket.nameSettings.callAfterChange = True
        socket.nameSettings.unique = True
        socket.removeable = True
        socket.moveable = True
        socket.customName = name

    def getSocketFromOtherNode(self, link):
        if link.from_node == self:
            return link.to_socket
        return link.from_socket

    def makeLink(self, socketA, socketB):
        if socketA.is_output:
            self.id_data.links.new(socketB, socketA)
        else:
            self.id_data.links.new(socketA, socketB)

    def execute(self, inputs):
        outputs = {}
        self.errorMessage = ""

        scriptLocals = {}
        for socket in self.inputs:
            if socket.name == emptySocketName: continue
            scriptLocals[socket.customName] = inputs[socket.identifier]

        try:
            exec(self.getScript(), scriptLocals, scriptLocals)
            for socket in self.outputs:
                if socket.name == emptySocketName: continue
                outputs[socket.identifier] = scriptLocals[socket.customName]
        except BaseException as e:
            self.errorMessage = str(e)
            for socket in self.outputs:
                if socket.identifier not in outputs:
                    outputs[socket.identifier] = socket.getValue()
        return outputs

    def getScript(self):
        textBlock = bpy.data.texts.get(self.textBlockName)
        if textBlock:
            return textBlock.as_string()
        return ""

    def buildFromText(self, text):
        lines = text.split("\n")
        state = "none"

        scriptLines = []

        for line in lines:
            if state == "none":
                if re.match("[Ii]nputs:", line):
                    state = "inputs"
                    continue
            elif state == "inputs":
                if re.match("[Oo]utputs:", line):
                    state = "outputs"
                    continue
                match = re.search("\s*(\w+)\s*-\s*(.+)", line)
                if match:
                    self.appendSocket(self.inputs, toIdName(match.group(2).strip()), match.group(1))
            elif state == "outputs":
                if re.match("[Ss]cript:", line):
                    state = "script"
                    continue
                match = re.search("\s*(\w+)\s*-\s*(.+)", line)
                if match:
                    self.appendSocket(self.outputs, toIdName(match.group(2).strip()), match.group(1))
            elif state == "script":
                scriptLines.append(line)

        scriptText = "\n".join(scriptLines)
        textBlock = self.getTextBlockWithText(scriptText)
        self.textBlockName = textBlock.name
        self.hideEditableElements = True

    def customSocketNameChanged(self, socket):
        if socket.name != emptySocketName:
            if self.enableUINameConversion:
                socket.name = toInterfaceName(socket.customName)
            else:
                socket.name = socket.customName

    def getTextBlockWithText(self, text):
        for textBlock in bpy.data.texts:
            if textBlock.as_string() == text:
                return textBlock
        textBlock = bpy.data.texts.new("script")
        textBlock.from_string(text)
        return textBlock


class OpenNewScript(bpy.types.Operator):
    bl_idname = "an.open_new_script"
    bl_label = "New Keyframe"
    bl_description = "Create a new text block (hold ctrl to open a new text editor)"

    nodeTreeName = StringProperty()
    nodeName = StringProperty()

    def invoke(self, context, event):
        node = getNode(self.nodeTreeName, self.nodeName)
        textBlock = bpy.data.texts.new("script")
        node.textBlockName = textBlock.name

        if event.ctrl or event.shift or event.alt:
            area = bpy.context.area
            area.type = "TEXT_EDITOR"
            area.spaces.active.text = textBlock
            bpy.ops.screen.area_split(direction = "HORIZONTAL", factor = 0.7)
            area.type = "NODE_EDITOR"

        return {'FINISHED'}

    def getAreaByType(self, type):
        for area in bpy.context.screen.areas:
            if area.type == type: return area
        return None


class AppendSocket(bpy.types.Operator):
    bl_idname = "an.append_socket_to_script_node"
    bl_label = "Append Socket to Script Node"
    bl_description = "Append a new socket to this node"

    nodeTreeName = StringProperty()
    nodeName = StringProperty()
    makeOutputSocket = BoolProperty()

    def execute(self, context):
        node = getNode(self.nodeTreeName, self.nodeName)
        type = toIdName(node.selectedSocketType)
        if self.makeOutputSocket:
            node.appendSocket(node.outputs, type, getPossibleSocketName(node, "socket"))
        else:
            node.appendSocket(node.inputs, type, getPossibleSocketName(node, "socket"))

        return {'FINISHED'}


class ExportScriptNode(bpy.types.Operator):
    bl_idname = "an.export_script_node"
    bl_label = "Export Script Node"
    bl_description = "Copy a text that describes the full script node"

    nodeTreeName = StringProperty()
    nodeName = StringProperty()

    def execute(self, context):
        node = getNode(self.nodeTreeName, self.nodeName)
        socketLines = []
        socketLines.append("Inputs:")
        for socket in node.inputs[:-1]:
            socketLines.append(socket.customName + " - " + socket.dataType)
        socketLines.append("\nOutputs:")
        for socket in node.outputs[:-1]:
            socketLines.append(socket.customName + " - " + socket.dataType)

        scriptText = "Script:\n"
        scriptText += node.getScript()

        exportText = "\n".join(socketLines)	+ "\n\n" + scriptText
        context.window_manager.clipboard = exportText
        return {'FINISHED'}
