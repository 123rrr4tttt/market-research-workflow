# theme nodes
## property: manual, not runnable
## input: none
## func: AI chat to figure out report structure and sections; generate a markdown file, save to local
## output: the file path of markdown

# markdown nodes
## property: runnable
## input: the file path of markdown (from local user file selection or any nodes that work on current markdown and return the path)
## func: provide markdown file to be worked on (file in the blank)
## output: file path of markdown

# populate section nodes
## property: runnable
## input: file path of markdown
## func: populate into 
