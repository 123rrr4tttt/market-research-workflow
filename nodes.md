# markdown nodes
## input: 
1. file path of the markdown to be created, opened
## output
1. file path of markdown
## widgets: 
1. input file path text box (read write)
3. output file path text box (read only)
## func: 
1. provide markdown file to be worked on
2. when select create/open, if file path does not exist, create path and files; when select copy, make a copy but if not exist, fallback to create/open
3. must not be empty, default to a default path (workspace folder) and file in the project

# populate nodes
## input
1. file path of markdown
## output:
1. generate tree graph of sections nodes in hierarchical order
## widgets:
1. input file path text box
2. section nodes (as a result of running)
3. colomns of hierarchy wrapped in dashed lines, each has a AI chat widget at the top to help manage sections of each hierarchy, but can only manage sections of current and lower hierarchies
4. in the ending hierarchy of nodes, force connect all nodes to another markdown node as a way of selecting saving path of edit result, default to itself, this file is generated when run button clicked if needed
5. a run button
## func:
1. At its output, first directly connect to a section head node representing the title of the markdown, if empty generate an empty one; following that a tree graph of section nodes populating from left to right according to markdown content, each hierarchy should strictly align in colomns
2. At its output, force generate a node for managing reference but not included in the first column
3. double click the colomn empty space create a new node in this hierarchy; double click the node create a subsection for this node in the next hierarchy


# section nodes
## input: 
1. upper hierarchy nodes (forced, non editable)
## output: 
2. next hierarchy (forced, non editable); if ending hierarcy force connect to the saving markdown node
## widgets: 
1. section title text box (if empty leave dummy words)
2. section content text box (if empty leave dummy words)
3. cross mark to delete
## func: 
1. read, display titles and contents
2. save changes in the destination markdown on each edit
