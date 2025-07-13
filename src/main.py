#!/usr/bin/env python3
import os
import json
import re
import argparse
from pathlib import Path

# This script converts a Bruno API collection into Markdown documentation.
#
# It walks through the specified Bruno collection folder, reads the `.bru` files,
# parses them to extract request details (method, URL, parameters, etc.),
# and generates a corresponding structure of Markdown files in an output directory.
#
# Usage:
# python bruno_to_markdown.py /path/to/your/bruno/collection -o /path/to/output/docs
def parse_bru_file(file_path: Path) -> dict | None:
	"""
	Parses a single .bru file to extract relevant API request information.

	The .bru format is a custom, block-based format. This function uses regular
	expressions to find and parse the 'meta', HTTP method (get, post, etc.),
	and parameter blocks.

	Args:
		file_path: The path to the .bru file.

	Returns:
		A dictionary containing the parsed data (name, method, url, params, etc.),
		or None if parsing fails or it's not a request file.
	"""
	try:
		content = file_path.read_text(encoding='utf-8')
		
		# --- Parse meta block ---
		meta_match = re.search(r'meta\s*\{([\s\S]*?)\}', content)
		if not meta_match:
			return None # Not a valid request file without a meta block

		meta_content = meta_match.group(1)
		name_match = re.search(r'name:\s*(.*)', meta_content)
		seq_match = re.search(r'seq:\s*(\d+)', meta_content)

		# --- Parse HTTP method block (e.g., get, post) ---
		# This regex finds the first block that is a common HTTP method.
		method_match = re.search(r'(get|post|put|patch|delete|options|head)\s*\{([\s\S]*?)\}', content, re.IGNORECASE)
		if not method_match:
			return None # No HTTP method found

		method = method_match.group(1).upper()
		method_content = method_match.group(2)
		url_match = re.search(r'^url:\s*(.+)$', method_content, re.MULTILINE)

		# --- Parse various parameter blocks ---
		def parse_params_block(block_name: str, text: str) -> dict:
			"""Helper to parse key-value pairs from a block."""
			params = {}
			# Regex to find a specific block and its content
			block_match = re.search(fr'{block_name}\s*\{{([\s\S]*?)\}}', text)
			if block_match:
				block_content = block_match.group(1).strip()
				# Find all key-value pairs within the block
				lines = block_content.split('\n')
				for line in lines:
					line = line.strip()
					if ':' in line:
						key, value = line.split(':', 1)
						params[key.strip()] = value.strip()
			return params

		path_params = parse_params_block('params:path', content)
		query_params = parse_params_block('params:query', content)
		headers = parse_params_block('headers', content)

		# --- Parse body ---
		body_content = ""
		body_match = re.search(r'body:(\w+)\s*\{([\s\S]*?)\}', content, re.DOTALL)
		if body_match:
			body_type = body_match.group(1)
			raw_body = body_match.group(2).strip()
			# For JSON, we try to format it nicely
			if body_type.lower() == 'json':
				try:
					# Remove the outer braces that are part of the bru syntax
					json_body_match = re.search(r'\{([\s\S]*)\}', raw_body, re.DOTALL)
					if json_body_match:
						json_str = json_body_match.group(0)
						parsed_json = json.loads(json_str)
						body_content = f"```json\n{json.dumps(parsed_json, indent=2)}\n```"
					else:
						body_content = f"```json\n{raw_body}\n```"
				except json.JSONDecodeError:
					body_content = f"```\n{raw_body}\n```" # Fallback for invalid JSON
			else:
				body_content = f"```{body_type}\n{raw_body}\n```"


		return {
			"name": name_match.group(1).strip() if name_match else "Unnamed Request",
			"seq": int(seq_match.group(1)) if seq_match else 999,
			"method": method,
			"url": url_match.group(1).strip() if url_match else "No URL found",
			"path_params": path_params,
			"query_params": query_params,
			"headers": headers,
			"body": body_content
		}
	except Exception as e:
		print(f"Error parsing file {file_path}: {e}")
		return None

def generate_request_markdown(req_data: dict) -> str:
	"""
	Generates the Markdown string for a single API request.
	"""
	md = []
	md.append(f"### {req_data['name']}\n")
	md.append(f"**`{req_data['method']}`** `{req_data['url']}`\n")

	def generate_table(title: str, params: dict):
		if not params:
			return
		md.append(f"**{title}**\n")
		md.append("| Name | Value / Description |")
		md.append("|------|---------------------|")
		for key, value in params.items():
			md.append(f"| `{key}` | {value} |")
		md.append("")

	generate_table("Path Parameters", req_data['path_params'])
	generate_table("Query Parameters", req_data['query_params'])
	generate_table("Headers", req_data['headers'])
	
	if req_data['body']:
		md.append("**Body**\n")
		md.append(req_data['body'])

	return "\n".join(md) + "\n---\n"

def main():
	"""
	Main function to drive the script.
	"""
	parser = argparse.ArgumentParser(
		description="Convert a Bruno API collection to Markdown documentation."
	)
	parser.add_argument(
		"collection_path",
		type=str,
		help="Path to the root directory of the Bruno collection."
	)
	parser.add_argument(
		"-o", "--output",
		type=str,
		default="bruno-docs",
		help="Path to the output directory for the Markdown files. Defaults to 'bruno-docs'."
	)
	args = parser.parse_args()

	collection_path = Path(args.collection_path)
	output_path = Path(args.output)

	# --- Validate input path ---
	bruno_json_path = collection_path / "bruno.json"
	if not bruno_json_path.is_file():
		print(f"Error: 'bruno.json' not found in '{collection_path}'. Please provide a valid Bruno collection directory.")
		return

	try:
		with open(bruno_json_path, 'r', encoding='utf-8') as f:
			collection_info = json.load(f)
		collection_name = collection_info.get("name", collection_path.name)
		ignore_list = collection_info.get("ignore", [])
		ignore_list.extend(['.git', 'node_modules']) # Always ignore these
	except (json.JSONDecodeError, IOError) as e:
		print(f"Error reading or parsing bruno.json: {e}")
		return

	print(f"Starting conversion for collection: '{collection_name}'")
	print(f"Output will be saved to: '{output_path}'")

	# --- Create output directory ---
	output_path.mkdir(exist_ok=True)
	
	top_level_readme_content = [f"# API Documentation: {collection_name}\n"]
	top_level_folders = []

	# --- Walk through the collection directory ---
	for root, dirs, files in os.walk(collection_path):
		root_path = Path(root)
		
		# Skip ignored directories
		dirs[:] = [d for d in dirs if d not in ignore_list]

		# --- Process files in the current directory ---
		requests_data = []
		folder_name = root_path.name

		# Check for folder.bru to get a more descriptive folder name
		if 'folder.bru' in files:
			folder_bru_path = root_path / 'folder.bru'
			try:
				content = folder_bru_path.read_text(encoding='utf-8')
				name_match = re.search(r'name:\s*(.*)', content)
				if name_match:
					folder_name = name_match.group(1).strip()
			except Exception as e:
				print(f"Could not parse {folder_bru_path}: {e}")


		for file in files:
			if file.endswith('.bru') and file != 'folder.bru':
				file_path = root_path / file
				parsed_data = parse_bru_file(file_path)
				if parsed_data:
					requests_data.append(parsed_data)

		if not requests_data:
			continue

		# Sort requests by their sequence number
		requests_data.sort(key=lambda r: r.get('seq', 999))

		# --- Generate Markdown for the current folder ---
		relative_path = root_path.relative_to(collection_path)
		folder_output_dir = output_path / relative_path
		folder_output_dir.mkdir(parents=True, exist_ok=True)
		
		markdown_content = [f"# {folder_name}\n"]
		for req in requests_data:
			markdown_content.append(generate_request_markdown(req))

		# Write the folder's README.md
		readme_path = folder_output_dir / "README.md"
		readme_path.write_text("\n".join(markdown_content), encoding='utf-8')
		print(f"Generated: {readme_path}")
		
		# Add a link to the top-level README
		if root_path != collection_path:
			if root_path.parent == collection_path: # It's a top-level folder
				top_level_folders.append((folder_name, relative_path / "README.md"))

	# --- Generate the main README.md with links to sub-folders ---
	if top_level_folders:
		top_level_readme_content.append("## Endpoints\n")
		# Sort folders alphabetically for consistent output
		top_level_folders.sort()
		for name, path in top_level_folders:
			# Format path for Markdown link
			link_path = str(path).replace('\\', '/')
			top_level_readme_content.append(f"- [{name}]({link_path})")

	main_readme_path = output_path / "README.md"
	main_readme_path.write_text("\n".join(top_level_readme_content), encoding='utf-8')
	print(f"Generated: {main_readme_path}")

	print("\nConversion complete!")

if __name__ == "__main__":
	main()
