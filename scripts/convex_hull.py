"""
Test script to demonstrate convex hull optimization for encoding ladder generation.
"""

import json

import matplotlib.pyplot as plt
import numpy as np


# Simulating the convex hull computation
def parse_encoding_id(encoding_id: str):
    """Parse encoding ID to extract resolution and bitrate."""
    parts = encoding_id.split("_")
    resolution = parts[-2]  # e.g., "1280x720"
    bitrate_part = parts[-1]  # e.g., "4500k.mp4"
    bitrate = int(bitrate_part.split("k.")[0])
    return resolution, bitrate


def compute_convex_hull(quality_metrics):
    """Compute the convex hull (Pareto frontier) of quality-bitrate points."""
    # Parse encoding_id to extract resolution and bitrate
    parsed_metrics = []
    for metric in quality_metrics:
        resolution, bitrate = parse_encoding_id(metric["encoding_id"])
        parsed_metrics.append(
            {"encoding_id": metric["encoding_id"], "resolution": resolution, "bitrate": bitrate, "vmaf": metric["vmaf"]}
        )

    # Sort by bitrate
    sorted_metrics = sorted(parsed_metrics, key=lambda x: x["bitrate"])

    # Compute convex hull (upper envelope)
    hull_points = []
    max_vmaf_so_far = -float("inf")

    for point in sorted_metrics:
        if point["vmaf"] > max_vmaf_so_far:
            hull_points.append(point)
            max_vmaf_so_far = point["vmaf"]

    return hull_points


def refine_ladder_points(hull_points):
    """Refine ladder points to ensure reasonable spacing."""
    # Ensure hull points are sorted by bitrate (ascending)
    sorted_hull = sorted(hull_points, key=lambda x: x["bitrate"])

    # If we have very few points, return them all
    if len(sorted_hull) <= 4:
        return sorted_hull

    refined_points = []

    # Always include the lowest and highest bitrate points
    refined_points.append(sorted_hull[0])

    # Filter intermediate points to maintain reasonable spacing
    # Prefer keeping at least 1.5x bitrate jumps between ladder rungs
    last_added = sorted_hull[0]
    for point in sorted_hull[1:-1]:
        # Include the point if it's at least 1.5x the bitrate of the last added point
        # or if it's a resolution transition point (different resolution from the last)
        if point["bitrate"] >= last_added["bitrate"] * 1.5 or point["resolution"] != last_added["resolution"]:
            refined_points.append(point)
            last_added = point

    # Always include the highest bitrate point if not already added
    if sorted_hull[-1] != last_added:
        refined_points.append(sorted_hull[-1])

    return refined_points


def visualize_convex_hull(all_points, hull_points, refined_points=None):
    """Visualize all points and the convex hull."""
    plt.figure(figsize=(12, 8))

    # Create lists for plotting
    resolutions = sorted(list(set([p["resolution"] for p in all_points])))
    colors = plt.cm.tab10(np.linspace(0, 1, len(resolutions)))
    markers = ["o", "s", "^", "D", "p", "*", "x", "+"]

    # Plot all points, with different colors and markers for each resolution
    for i, resolution in enumerate(resolutions):
        resolution_points = [p for p in all_points if p["resolution"] == resolution]
        x = [p["bitrate"] for p in resolution_points]
        y = [p["vmaf"] for p in resolution_points]
        plt.scatter(x, y, c=[colors[i]], marker=markers[i % len(markers)], label=f"{resolution}", s=100, alpha=0.7)

    # Plot convex hull line
    hull_x = [p["bitrate"] for p in hull_points]
    hull_y = [p["vmaf"] for p in hull_points]
    plt.plot(hull_x, hull_y, "r-", linewidth=2, label="Convex Hull")

    # Plot hull points
    hull_scatter_x = [p["bitrate"] for p in hull_points]
    hull_scatter_y = [p["vmaf"] for p in hull_points]
    plt.scatter(hull_scatter_x, hull_scatter_y, c="red", s=150, marker="o", facecolors="none", linewidth=2, zorder=10)

    # Plot refined points if provided
    if refined_points:
        refined_x = [p["bitrate"] for p in refined_points]
        refined_y = [p["vmaf"] for p in refined_points]
        plt.scatter(refined_x, refined_y, c="green", s=200, marker="X", linewidth=2, zorder=11, label="Ladder Rungs")

    # Set plot properties
    plt.title("Video Encoding Quality vs. Bitrate with Convex Hull", fontsize=16)
    plt.xlabel("Bitrate (kbps)", fontsize=14)
    plt.ylabel("VMAF Score", fontsize=14)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend(fontsize=12)

    # Set axis limits
    plt.xlim(0, max([p["bitrate"] for p in all_points]) * 1.1)
    plt.ylim(min([p["vmaf"] for p in all_points]) * 0.9, 100)

    # Add annotations
    for point in hull_points:
        plt.annotate(
            f"{point['resolution']}\n{point['bitrate']}k",
            (point["bitrate"], point["vmaf"]),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
            fontsize=9,
        )

    plt.tight_layout()

    # In a real script, you'd save this to a file with plt.savefig()
    # For now, we'll just display it
    plt.show()


# Main function to execute the test
def main():
    # Load test data from step6.json
    with open("./output/step6.json", "r") as f:
        data = json.load(f)

    # Extract quality metrics
    quality_metrics = data["quality_metrics"]

    # Compute convex hull
    hull_points = compute_convex_hull(quality_metrics)

    # Refine ladder points
    refined_points = refine_ladder_points(hull_points)

    # Parse all metrics for visualization
    all_points = []
    for metric in quality_metrics:
        resolution, bitrate = parse_encoding_id(metric["encoding_id"])
        all_points.append({"resolution": resolution, "bitrate": bitrate, "vmaf": metric["vmaf"]})

    # Visualize results
    visualize_convex_hull(all_points, hull_points, refined_points)

    print("Convex Hull Points:")
    for point in hull_points:
        print(f"{point['resolution']} @ {point['bitrate']}k -> VMAF {point['vmaf']:.2f}")

    print("\nLadder Rungs After Refinement:")
    for point in refined_points:
        print(f"{point['resolution']} @ {point['bitrate']}k -> VMAF {point['vmaf']:.2f}")

    # Apply complexity-based adjustments
    complexity = "High"  # From the test data
    adjustment_factor = 1.15 if complexity == "High" else 1.0

    print(f"\nFinal Encoding Ladder (with {complexity} complexity adjustment {adjustment_factor:.2f}):")
    for point in refined_points:
        adjusted_bitrate = int(point["bitrate"] * adjustment_factor)
        width, height = point["resolution"].split("x")
        profile = "high" if int(width) >= 1280 else "main" if int(width) >= 640 else "baseline"
        print(f"{point['resolution']} @ {adjusted_bitrate}k ({profile}) -> Expected VMAF {point['vmaf']:.2f}")

    # Estimated savings (example calculation)
    estimated_savings = "10%" if complexity == "High" else "15%"
    print(f"\nEstimated savings: {estimated_savings}")


if __name__ == "__main__":
    main()
