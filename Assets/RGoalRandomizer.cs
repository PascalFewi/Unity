using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Perception.Randomization.Randomizers;



[Serializable]
[AddRandomizerMenu("NomadZ/R Goal Randomizer")]
public class RGoalRandomizer : Randomizer
{
    [Header("X Offset Range")]
    public float minOffsetx = -0.1f;
    public float maxOffsetx = 0.1f;

    public float minOffsety = -0.1f;
    public float maxOffsety = 0.1f;


    // Each object's position before the first offset. Offsets are applied to this,
    // not to the current position, so they don't accumulate into a random walk.
    Dictionary<Transform, Vector3> originalPositions;

    protected override void OnScenarioStart()
    {
        originalPositions = new Dictionary<Transform, Vector3>();
    }

    protected override void OnIterationStart()
    {
        // Generate once, shared by all tagged objects
        float offsetX = UnityEngine.Random.Range(minOffsetx, maxOffsetx);
        float offsetY = UnityEngine.Random.Range(minOffsety, maxOffsety);

        var tags = tagManager.Query<RGoalRandomizerTag>();
        foreach (var tag in tags)
        {
            var obj = tag.transform;
            if (!originalPositions.TryGetValue(obj, out Vector3 basePos))
            {
                basePos = obj.position;
                originalPositions[obj] = basePos;
            }
            obj.position = new Vector3(
                basePos.x + offsetX,
                basePos.y + offsetY,
                basePos.z
            );
        }
    }
}
