using UnityEditor;

// Same as JerseyRandomizerTagEditor: replaces Perception's tag editor so many robots can be edited at once.
[CustomEditor(typeof(RobotPlacementRandomizerTag)), CanEditMultipleObjects]
public class RobotPlacementRandomizerTagEditor : Editor
{
    public override void OnInspectorGUI() => DrawDefaultInspector();
}
