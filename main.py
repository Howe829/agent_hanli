import re
import pathlib
def main():
    print("Hello from agent-hanli!")


if __name__ == "__main__":
    pattern = re.compile(r"第.*章.*?")
    pattern1 = re.compile(r"第.*卷.*")
    title_set = set()
    base_path = pathlib.Path("./resources")
    with open("./resources/fanrenxxz-full.txt", "r", encoding="utf-8") as f:
        chapter_content = ""
        title = "简介"
        index = 0
        for line in f.readlines():
            result = re.match(pattern, line)
            result1 = re.match(pattern1, line.strip())
            if result1:
                dir_name = line.strip()
                if not dir_name.endswith("。"):
                    dir_path = base_path.joinpath(dir_name)
                    dir_path.mkdir(exist_ok=True)
                
            if result:
                if title not in title_set:
                    filename = f"{index:04}{title.strip()}.txt"
                    print(line)
                    filepath = dir_path.joinpath(filename)
                    with filepath.open(mode="w") as fw:
                        fw.write(chapter_content)
                    title_set.add(title)
                    index+=1
                chapter_content = line
                title = line
            else:
                chapter_content += line
        if chapter_content != title:
            filename = f"{index:04}{title.strip()}.txt"
            filepath = dir_path.joinpath(filename)
            with filepath.open(mode="w") as fw:
                fw.write(chapter_content)
            
            