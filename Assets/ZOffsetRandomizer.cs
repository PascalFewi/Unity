using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Perception.Randomization.Randomizers;



[Serializable]
[AddRandomizerMenu("NomadZ/Z Offset Randomizer")]
public class ZOffsetRandomizer : Randomizer
{
    [Header("X Offset Range")]
    public float minOffset = -0.1f;
    public float maxOffset = 0.1f;

    // Each object's position before the first offset. Offsets are applied to this,
    // not to the current position, so they don't accumulate into a random walk.
    Dictionary<Transform, Vector3> originalPositions;

    protected override void OnScenarioStart()
    {
        originalPositions = new Dictionary<Transform, Vector3>();
    }

    protected override void OnIterationStart()
    {
        var tags = tagManager.Query<ZOffsetRandomizerTag>();

        foreach (var tag in tags)
        {
            var obj = tag.transform;

            // Store original position safely per object
            if (!originalPositions.TryGetValue(obj, out Vector3 basePos))
            {
                basePos = obj.position;
                originalPositions[obj] = basePos;
            }

            float offset = UnityEngine.Random.Range(minOffset, maxOffset);

            obj.position = new Vector3(
                basePos.x,
                basePos.y,
                basePos.z + offset
            );
        }
    }
}