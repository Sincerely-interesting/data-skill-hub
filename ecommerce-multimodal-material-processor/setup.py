"""
电商多模态素材处理引擎 - 安装配置
"""
from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="ecommerce-multimodal-material-processor",
    version="1.0.0",
    author="E-commerce Material Processing Team",
    author_email="team@example.com",
    description="企业级电商多模态素材处理流水线（独立可运行版本）",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/ecommerce-material-processor",
    
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    
    python_requires=">=3.10",
    install_requires=requirements,
    
    entry_points={
        "console_scripts": [
            "ecommerce-processor=run_pipeline:main",
        ],
    },
    
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    
    keywords="e-commerce, multimodal, material-processing, labeling, archiving, AI, vision",
    
    include_package_data=True,
    zip_safe=False,
)