
## We welcome contributions! Follow these guidelines:

#### Before Starting
1. Check existing [issues](https://github.com/Tanmay-Bhatnagar22/TraceLens/issues)
2. Discuss major changes via new issue
3. Fork the repository

#### Development Workflow
1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make focused, atomic commits
3. Add or update tests for your changes
4. Run full test suite: `pytest tests/`
5. Update README if needed
6. Push to fork and submit pull request

#### Code Style
- Follow PEP 8 conventions
- Use type hints (`dict[str, Any]`, etc.)
- Write docstrings for all functions
- Aim for >80% test coverage
- Test both success and failure cases

#### Commit Message Format
```
[TYPE] Brief description

Longer explanation if needed.

Fixes #issue_number (if applicable)
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

#### Example Contribution
```python
# New feature with tests
def extract_custom_format(file_path: str) -> dict[str, Any]:
    """Extract metadata from custom format.
    
    Args:
        file_path: Path to file to extract
        
    Returns:
        Dictionary of extracted metadata
        
    Raises:
        ValueError: If file format is invalid
    """
    # Implementation...
    pass
```

### Reporting Issues

**Include**:
- OS and Python version
- Steps to reproduce
- Expected vs. actual behavior
- Error messages/stack traces
- Screenshot of GUI (if applicable)

**Format**:
```markdown
**Environment**: Windows 10, Python 3.10.5
**Description**: Brief issue description
**Steps**: 
1. ...
2. ...
**Expected**: ...
**Actual**: ...
```
