import sys
import os
import ast
from time import sleep
from utils import clean_dir
from constants import DEFAULT_DIR, DEFAULT_MODEL, DEFAULT_MAX_TOKENS


def generate_response(system_prompt, user_prompt, *args):
    import openai
    import tiktoken

    def reportTokens(prompt):
        encoding = tiktoken.encoding_for_model(DEFAULT_MODEL)
        # print number of tokens in light gray, with first 10 characters of prompt in green
        print(
            "\033[37m"
            + str(len(encoding.encode(prompt)))
            + " tokens\033[0m"
            + " in prompt: "
            + "\033[92m"
            + prompt[:50]
            + "\033[0m"
        )

    # Set up your OpenAI API credentials
    openai.api_key = os.environ["OPENAI_API_KEY"]

    messages = []
    messages.append({"role": "system", "content": system_prompt})
    reportTokens(system_prompt)
    messages.append({"role": "user", "content": user_prompt})
    reportTokens(user_prompt)
    # loop thru each arg and add it to messages alternating role between "assistant" and "user"
    role = "assistant"
    for value in args:
        messages.append({"role": role, "content": value})
        reportTokens(value)
        role = "user" if role == "assistant" else "assistant"

    params = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": 0,
    }

    # Send the API request
    keep_trying = True
    while keep_trying:
        try:
            response = openai.ChatCompletion.create(**params)
            keep_trying = False
        except Exception as e:
            # e.g. when the API is too busy, we don't want to fail everything
            print("Failed to generate response. Error: ", e)
            # Extract the length of the message from the error message
            if "That model is currently overloaded with other requests" in str(e):
                print("Model overloaded, waiting 10 seconds...")
                sleep(10)
            else:
                # from character 88 to the first space
                messageLength = int(str(e)[88:].split(" ")[0])
                oldMaxTokens = params["max_tokens"]
                params["max_tokens"] = 4097 - messageLength - 1
                if oldMaxTokens == params["max_tokens"]:
                    params["max_tokens"] = int(oldMaxTokens * .9)
                print("Decreasing max tokens to ",
                      params["max_tokens"], " and retrying...")
    params['max_tokens'] = DEFAULT_MAX_TOKENS

    # Get the reply from the API response
    reply = response.choices[0]["message"]["content"]
    return reply


def generate_file(
    filename, filepaths_string=None, shared_dependencies=None, prompt=None
):
    # call openai api with this prompt
    filecode = generate_response(
        f"""You are an AI developer who is trying to write a program that will generate code for the user based on their intent.

    the app is: {prompt}

    the files we have decided to generate are: {filepaths_string}

    the shared dependencies we have decided on are: {shared_dependencies}

    only write valid code for the given filepath and file type, and return only the code.
    do not add any other explanation, only return valid code for that file type.
    """,
        f"""
    We have broken up the program into per-file generation.
    Now your job is to generate only the code for the file {filename}.
    Make sure to have consistent filenames if you reference other files we are also generating.

    Remember that you must obey 3 things:
       - you are generating code for the file {filename}
       - do not stray from the names of the files and the shared dependencies we have decided on
       - MOST IMPORTANT OF ALL - the purpose of our app is {prompt} - every line of code you generate must be valid code. Do not include code fences in your response, for example

    Bad response:
    ```javascript
    console.log("hello world")
    ```

    Good response:
    console.log("hello world")

    Begin generating the code now.

    """,
    )

    return filename, filecode


def main(prompt, directory=DEFAULT_DIR, file=None):
    # read file from prompt if it ends in a .md filetype
    if prompt.endswith(".md"):
        with open(prompt, "r") as promptfile:
            prompt = promptfile.read()

    print("hi its me, 🐣the smol developer🐣! you said you wanted:")
    # print the prompt in green color
    print("\033[92m" + prompt + "\033[0m")

    # example prompt:
    # a Chrome extension that, when clicked, opens a small window with a page where you can enter
    # a prompt for reading the currently open page and generating some response from openai

    # call openai api with this prompt
    filepaths_string = generate_response(
        """You are an AI developer who is trying to write a program that will generate code for the user based on their intent.

    When given their intent, create a complete, exhaustive list of filepaths that the user would write to make the program and a brief description of what each of these files should contain.
    Feel free to break file into smaller, single responsibility files as much as possible.

    output the response as a python dictionary, where the keys are the filepaths and the values are the description of what should be in that file in plain english.
    do not add any other explanation, only return a python list of strings. CODE ONLY. NO EXPLANATION. NO CODE FENCES. ONLY CODE.
    """,
        prompt,
    )
    print(filepaths_string)
    # parse the result into a python list
    list_actual = {}
    try:
        list_actual = ast.literal_eval(filepaths_string)
        # if shared_dependencies.md is there, read it in, else set it to None
        shared_dependencies = None
        if os.path.exists("shared_dependencies.md"):
            with open("shared_dependencies.md", "r") as shared_dependencies_file:
                shared_dependencies = shared_dependencies_file.read()

        if file is not None:
            # check file
            print("file", file)
            filename, filecode = generate_file(
                file,
                filepaths_string=filepaths_string,
                shared_dependencies=shared_dependencies,
                prompt=prompt,
            )
            write_file(filename, filecode, directory)
        else:
            clean_dir(directory)

            gen_files = "\n".join(
                [f"- {file} : {desc}" for file, desc in list_actual.items()])

            write_file("filepaths.md", gen_files, directory)

            # understand shared dependencies
            shared_dependencies = generate_response(
                f"""You are an AI developer who is trying to write a program that will generate code for the user based on their intent.

            In response to the user's prompt:

            ---
            the app is: {{prompt}}
            ---

            the files we have decided to generate are: 
            {gen_files}

            Now that we have a dictionary of files, we need to understand what dependencies they share.
            Please name and briefly describe what is shared between the files we are generating, including exported variables, data schemas, message names, and function names.
            Exclusively focus on the names of the shared dependencies, and do not add any other explanation.
            """,
                prompt,
            )
            print(shared_dependencies)
            # write shared dependencies as a md file inside the generated directory
            write_file("shared_dependencies.md",
                       shared_dependencies, directory)

            for name in list_actual:
                filename, filecode = generate_file(
                    name,
                    filepaths_string=gen_files,
                    shared_dependencies=shared_dependencies,
                    prompt=prompt,
                )
                write_file(filename, filecode, directory)

    except ValueError:
        print("Failed to parse result: " + result)


def write_file(filename, filecode, directory):
    # Output the filename in blue color
    print("\033[94m" + filename + "\033[0m")
    print(filecode)

    file_path = directory + "/" + filename
    dir = os.path.dirname(file_path)
    os.makedirs(dir, exist_ok=True)

    # Open the file in write mode
    with open(file_path, "w") as file:
        # Write content to the file
        file.write(filecode)


if __name__ == "__main__":

    # Check for arguments
    if len(sys.argv) < 2:

        # Looks like we don't have a prompt. Check if prompt.md exists
        if not os.path.exists("prompt.md"):

            # Still no? Then we can't continue
            print("Please provide a prompt")
            sys.exit(1)

        # Still here? Assign the prompt file name to prompt
        prompt = "prompt.md"

    else:
        # Set prompt to the first argument
        prompt = sys.argv[1]

    # Pull everything else as normal
    directory = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DIR
    file = sys.argv[3] if len(sys.argv) > 3 else None

    # Run the main function
    main(prompt, directory, file)
