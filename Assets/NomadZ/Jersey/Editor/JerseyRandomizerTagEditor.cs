using UnityEditor;

// Perception's RandomizerTagEditor (applied to every RandomizerTag) has no multi-object
// support; this more specific editor replaces it so many robots can be edited at once.
[CustomEditor(typeof(JerseyRandomizerTag)), CanEditMultipleObjects]
public class JerseyRandomizerTagEditor : Editor
{
    public override void OnInspectorGUI() => DrawDefaultInspector();
}
