import os
import base64
import json
from flask import Flask, render_template, request
from dotenv import load_dotenv
import openai
from flask import url_for

ASP = """You are a visualization linter designed to analyze various types of data visualizations and detect issues based on a set of rules. Your task is to detect the type of plot from the uploaded image or code, extract the necessary attributes from the plot, find appropriate thresholds for each rule depending on the plot and data, and then apply the rules to identify any issues."""

prompt = """Steps:

Detect the type of plot from the uploaded image or code. The plot could be one of the following:

Line Plot
Bar Plot
Pie Chart
Scatter Plot
Histogram
Box Plot
Heatmap
Area Plot
Treemap

Extract the relevant attributes for the detected plot type. For each plot, extract the following attributes based on the associated rules:

Line Plot: axis scaling, number of lines, baseline, gridlines, time intervals, line styles/colors, missing data points, dual axis, readability
Bar Plot: axis scaling, bar widths, y-axis baseline, gridlines, category order, 3D bar usage, bar overlap, color choices, number of categories, dual axis, readability
Pie Chart: number of slices, slice colors, starting angle, slice sizes, labels/legends, exploding slices, readability
Scatter Plot: point overlap, axis scaling, y-axis baseline, labels/legends, gridlines, color/marker usage, outlier highlighting, data density, trend lines, dual axis, readability
Histogram: bin width, number of bins, y-axis baseline, gridlines, bin overlap, bin placement, normalization, axis scaling, readability
Box Plot: outliers, box size, axis labels, y-axis baseline, category count, IQR explanation, median/quartile lines, scale consistency, readability
Heatmap: color scheme, legend, number of variables, color saturation, normalization, aspect ratio, data labels, readability
Area Plot: overlapping areas, proportions, y-axis baseline, number of areas, category differentiation, color consistency, gradient usage, readability
Treemap: number of items, color scheme, hierarchy explanation, block size distribution, nesting levels, interactivity, readability

Find the appropriate thresholds for each rule based on the plot type and data. The thresholds will guide whether an issue exists. These thresholds should be based on common visualization best practices and may be context-dependent on the dataset. Examples of thresholds for different rules might include:

Line Plot:-
Scale or axis limits: The y-axis should generally start at zero, unless there’s a clear reason for not doing so.
Number of lines: A plot with more than 5-7 lines may become overcrowded, making it difficult to distinguish between them.
Gridlines: Too many gridlines (e.g., more than 5 horizontal or vertical lines) can distract from the data.
Bar Plot:-
Bar widths: All bars in a bar chart should have consistent widths.
Y-axis baseline: The y-axis should start at zero, unless there's a valid reason for starting it at a higher value.
Overlapping bars: Bars should not overlap unless it is a stacked bar plot.
Category ordering: Categories should be ordered logically (e.g., by size, alphabetically, or chronologically).
Pie Chart:-
Number of slices: Pie charts should have no more than 5-7 slices.
Slice sizes: Each slice should accurately represent the proportion of the total, and there should be no visual distortion.
Labels/Legends: All slices should be labeled or there should be a clear legend.
Scatter Plot:-
Point overlap: If more than 20 percent of the points overlap, it may be necessary to reduce marker size or use transparency.
Axis scaling: Axes should use appropriate scaling to show the relationship between variables clearly.
Histogram:-
Bin width: Bins should have a consistent width or be chosen in a way that represents the data distribution clearly.
Number of bins: Too few bins (less than 5) can hide trends, and too many bins (more than 20) can create clutter.
Box Plot:-
Category count: A box plot with more than 10 categories might be too cluttered to interpret effectively.
Heatmap:-
Color scheme: Avoid color schemes that are hard to distinguish, such as red-green for colorblind users.
Aspect ratio: The heatmap should not be overly stretched or compressed, and the aspect ratio should reflect the number of rows and columns accurately.
Area Plot:-
Overlapping areas: Overlapping areas should be minimal, as they can obscure trends and make the plot harder to read.
Y-axis baseline: Like line plots, area plots should ideally start at zero to avoid exaggerating differences.
Treemap:-
Number of items: A treemap with more than 20 blocks may become too crowded to interpret effectively.
Block size consistency: Each block should accurately represent its data value, and inconsistencies in size may indicate a problem.

Once the thresholds are determined, apply the rules to identify any issues in the plot based on these thresholds. For each rule, check whether the plot violates any of the thresholds, and if so, report the detected issue.

"""

# Updated detection prompt instructing to output ONLY the chart type name.
DETECTION_PROMPT = (
    "Detect the type of chart represented by the input below. "
    "Respond with only the chart type name (e.g., 'Line Plot', 'Bar Plot', 'Pie Chart', 'Scatter Plot', 'Histogram', 'Box Plot', 'Heatmap', 'Area Plot', 'Treemap', etc.) with no additional text."
)

# Path to JSON file containing chart-specific prompts.
CHART_PROMPTS_FILE = "chart_prompts.json"

# Load environment variables from .env file
load_dotenv()
app = Flask(__name__)
openai_api_key = os.getenv("OPENAI_API_KEY")

# Ensure the directory for saving images exists
IMAGE_UPLOAD_PATH = os.path.join('static', 'images')
if not os.path.exists(IMAGE_UPLOAD_PATH):
    os.makedirs(IMAGE_UPLOAD_PATH)

def initialize_openai_client():
    return openai.OpenAI(api_key=openai_api_key)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def load_chart_prompt(chart_type):
    try:
        with open(CHART_PROMPTS_FILE, "r") as f:
            prompts = json.load(f)
        # Try to fetch prompt for detected chart type; if not found, fallback to "Other Charts"
        return prompts.get(chart_type) or prompts.get("Other Charts")
    except Exception as e:
        print(f"Error loading {CHART_PROMPTS_FILE}: {e}")
        return None

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        code = request.form.get('code') or ""
        code = code.strip()
        image = request.files.get("image")
        image_provided = image and image.filename != ""

        # Check for both inputs provided
        if code and image_provided:
            error_message = "Both code and image not accepted"
            return render_template("index.html", error_message=error_message)

        # Check for no input provided
        if not code and not image_provided:
            error_message = "Please provide either code or image input"
            return render_template("index.html", error_message=error_message)

        client = initialize_openai_client()

        try:
            # ----------------------
            # Step 1: Detect chart type
            # ----------------------
            if code:
                detection_message = f"{DETECTION_PROMPT}\n\nChart Code:\n{code}"
                detection_messages = [
                    {"role": "system", "content": "You are a chart detection agent."},
                    {"role": "user", "content": detection_message}
                ]
            elif image_provided:
                # Save and encode image
                image_path = os.path.join(IMAGE_UPLOAD_PATH, image.filename)
                image.save(image_path)
                base64_image = encode_image(image_path)
                detection_messages = [
                    {"role": "system", "content": "You are a chart detection agent."},
                    {"role": "user", "content": [
                        {"type": "text", "text": DETECTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ]

            detection_completion = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=50,
                messages=detection_messages
            )
            # Extract the chart type and strip any whitespace.
            chart_type = detection_completion.choices[0].message.content.strip()
            print(f"Detected chart type: {chart_type}")

            # Load chart-specific prompt from JSON file.
            chart_specific_prompt = prompt + load_chart_prompt(chart_type)
            print(chart_specific_prompt)
            if not chart_specific_prompt:
                error_message = f"Chart type '{chart_type}' not recognized and no fallback prompt available."
                return render_template("index.html", error_message=error_message)

            # ----------------------
            # Step 2: Get detailed fixes using chart-specific prompt
            # ----------------------
            if code:
                second_prompt = f"{chart_specific_prompt}\n\nChart Code:\n{code}\n\nAfter listing the detected issues, if any of the identified issues are related to the data-ink principle (for example, excessive non-data ink such as redundant gridlines or decorative elements that do not contribute to data clarity), then generate the corrected code for the same plot that fixes only those data-ink principle related issues."
                fix_messages = [
                    {"role": "system", "content": ASP},
                    {"role": "user", "content": second_prompt}
                ]
            elif image_provided:
                # For image-based input, reuse the saved & encoded image.
                second_prompt_content = [
                    {"type": "text", "text": chart_specific_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
                fix_messages = [
                    {"role": "system", "content": ASP},
                    {"role": "user", "content": second_prompt_content}
                ]

            fix_completion = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=1000,
                messages=fix_messages
            )
            response_text = fix_completion.choices[0].message.content
            uploaded_image_url = url_for('static', filename='images/' + image.filename)
            return render_template("index.html", response_text=response_text, uploaded_image_url=uploaded_image_url)
            #return render_template("index.html", response_text=response_text)

        except Exception as e:
            error_message = f"An error occurred: {e}"
            return render_template("index.html", error_message=error_message)

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
